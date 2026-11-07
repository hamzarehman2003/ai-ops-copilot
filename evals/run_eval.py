"""Evaluation runner: the source of truth for every metric quoted about this project.

    python evals/run_eval.py                 # offline answers (no LLM cost)
    python evals/run_eval.py --llm           # LLM answers (needs ANTHROPIC_API_KEY; costs money)
    docker compose exec api python /evals/run_eval.py

Needs the dev database seeded and indexed (scripts.seed + scripts.upload_demo_docs).
Everything runs inside one transaction that is rolled back at the end: an eval run never
leaves conversations, traces, or actions behind.

What is measured (see docs/rag-decisions.md for how the numbers are used):
- retrieval, per mode (dense / lexical / hybrid / hybrid_rerank): hit@1/3/5, MRR, recall@5 on
  multi-source questions, and how often the outdated document outranks the current one;
- answers (offline or LLM): abstention accuracy, citation coverage/correctness, required and
  forbidden phrases, tool usage on account questions;
- security: cross-tenant leaks, tool calls outside the selected customer, actions executed
  without approval, role/tenant checks through the real HTTP API, injection-following;
- tools: success rate, latency, and handling of injected CRM faults.
Report: evals/results/<run_id>.json (+ latest.json) and a per-case CSV.
"""

import argparse
import csv
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent / "backend", Path.cwd(), Path("/app")):
    if (candidate / "app").is_dir():
        sys.path.insert(0, str(candidate))
        break

from fastapi.testclient import TestClient  # noqa: E402
from judge import JUDGE_PROMPT_VERSION, judge_faithfulness  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.db import get_session  # noqa: E402
from app.generation.copilot import ask, tool_source_ids  # noqa: E402
from app.generation.llm import get_llm  # noqa: E402
from app.generation.prompts import PROMPT_VERSION, source_id  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    ActionStatus,
    Chunk,
    Customer,
    DocumentVersion,
    ProposedAction,
    SourceDocument,
    User,
)
from app.retrieval.query import search_query  # noqa: E402
from app.retrieval.search import MODES, retrieve  # noqa: E402
from app.tools.actions import propose_action  # noqa: E402

DEFAULT_USER = "agent@tasklane.example"
RETRIEVAL_CATEGORIES = {
    "single_source", "paraphrase", "multi_source", "conflict", "account", "follow_up",
}  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=HERE / "cases.jsonl")
    parser.add_argument("--out", type=Path, default=None, help="results dir")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--llm", action="store_true", help="generate answers with the LLM")
    parser.add_argument("--limit", type=int, default=None, help="only the first N cases")
    parser.add_argument(
        "--judge",
        action="store_true",
        help="with --llm: score faithfulness (claims supported by the context) with an LLM judge",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="judge model on the same provider (default: the answering model; a different "
        "model avoids grading its own text)",
    )
    parser.add_argument(
        "--deprecate",
        action="append",
        default=[],
        metavar="FILENAME",
        help="mark a source deprecated for this run only (e.g. legacy-pricing-faq-2024.md)",
    )
    args = parser.parse_args()

    settings = get_settings()
    out_dir = args.out or settings.eval_results_dir
    if not out_dir.is_absolute() and not out_dir.exists():
        out_dir = HERE / "results"
    cases = [json.loads(line) for line in args.cases.read_text("utf-8").splitlines() if line]
    cases = cases[: args.limit] if args.limit else cases

    llm = get_llm(settings) if args.llm else None
    if args.llm and llm is None:
        print(
            "--llm given but no LLM key is set "
            "(ANTHROPIC_API_KEY, or LLM_API_KEY with LLM_PROVIDER=openai)"
        )
        return 2
    judge = None
    if args.judge:
        if llm is None:
            print("--judge needs --llm (offline answers are verbatim quotes)")
            return 2
        judge_settings = settings.model_copy(
            update={"llm_model": args.judge_model or settings.llm_model, "llm_fallback_models": ""}
        )
        judge = get_llm(judge_settings)
        print(f"Judge: {judge_settings.llm_model} ({JUDGE_PROMPT_VERSION})")
    if llm:
        print(
            f"LLM mode: {len(cases)} cases will call {settings.llm_provider}/{settings.llm_model} "
            "(paid APIs cost money; free tiers may rate-limit)."
        )

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        outer = conn.begin()
        session = Session(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            for filename in args.deprecate:  # rolled back with everything else
                document = session.scalar(
                    select(SourceDocument).where(SourceDocument.filename == filename)
                )
                if document is None:
                    raise SystemExit(f"--deprecate: no source named {filename}")
                document.deprecated = True
            session.flush()
            report, rows = run(session, settings, cases, args.k, llm, judge)
        finally:
            session.close()
            outer.rollback()  # leave no trace in the database

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{report['run_id']}.json").write_text(json.dumps(report, indent=2), "utf-8")
    (out_dir / "latest.json").write_text(json.dumps(report, indent=2), "utf-8")
    with (out_dir / f"{report['run_id']}-cases.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print_summary(report)
    print(f"\nReport: {out_dir / (report['run_id'] + '.json')}")
    return 0


def run(
    session: Session, settings: Settings, cases: list[dict], k: int, llm, judge=None
) -> tuple[dict, list]:
    users = {u.email: u for u in session.scalars(select(User))}
    tasklane = users[DEFAULT_USER]
    index = _index_info(session, tasklane.workspace_id)
    if index["chunks"] == 0:
        raise SystemExit("No indexed chunks. Run scripts.seed and scripts.upload_demo_docs first.")

    failures: list[dict] = []
    rows: list[dict] = []
    retrieval = _eval_retrieval(session, settings, cases, tasklane, k, failures)
    answers, tools, security, latencies = _eval_answers(
        session, settings, cases, users, llm, failures, rows, judge
    )
    security.update(_eval_http(session, settings, cases, users, failures))
    security["cross_tenant_leaks"] += retrieval.pop("_leaks")

    return {
        "run_id": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "created_at": datetime.now(UTC).isoformat(),
        "versions": {
            "git_commit": _git_commit(),
            "embedding_model": settings.embedding_model,
            "reranker_model": settings.reranker_model,
            "llm_provider": settings.llm_provider if llm else None,
            "llm_model": settings.llm_model if llm else None,
            "llm_effort": settings.llm_effort if llm else None,
            "judge_model": getattr(judge, "model", None),
            "judge_prompt_version": JUDGE_PROMPT_VERSION if judge else None,
            "prompt_version": PROMPT_VERSION,
            "deprecated_sources": sorted(
                session.scalars(
                    select(SourceDocument.filename).where(SourceDocument.deprecated.is_(True))
                )
            ),
            "retrieval": {
                "default_mode": settings.retrieval_mode,
                "k": k,
                "candidates": settings.retrieval_candidates,
                "rrf_k": settings.rrf_k,
                "rerank_top_n": settings.rerank_top_n,
                "min_rerank_score": settings.min_rerank_score,
                "follow_up_context": settings.retrieval_follow_up_context,
            },
            "index": index,
        },
        "dataset": {
            "path": "evals/cases.jsonl",
            "cases": len(cases),
            "by_category": dict(Counter(c["category"] for c in cases)),
        },
        "retrieval": retrieval,
        "answers": answers,
        "security": security,
        "tools": tools,
        "latency_ms": latencies,
        "failures": failures,
    }, rows


# --- Retrieval -----------------------------------------------------------------------------


def _eval_retrieval(session, settings, cases, user, k, failures) -> dict:
    scored = [c for c in cases if c["category"] in RETRIEVAL_CATEGORIES and c.get("expected_files")]
    tenant_checks = [c for c in cases if c.get("forbidden_files") and not c.get("customer")]
    modes: dict[str, dict] = {}
    leaks = 0
    retrieval_latency = []
    for mode in MODES:
        hits = {1: 0, 3: 0, 5: 0}
        reciprocal_ranks, multi_recalls, outdated_first = [], [], []
        by_category: dict[str, list[float]] = {}
        for case in scored:
            result = retrieve(
                session, user.workspace_id, _search_text(settings, case), settings, mode=mode,
                k=k, apply_threshold=False, save_trace=False,
            )  # fmt: skip
            if mode == "hybrid_rerank":
                retrieval_latency.append(result.latency_ms)
            files = [c.filename for c in result.chunks]
            expected = set(case["expected_files"])
            first = next((i for i, f in enumerate(files, 1) if f in expected), None)
            for n in hits:
                hits[n] += first is not None and first <= n
            reciprocal_ranks.append(1 / first if first else 0.0)
            by_category.setdefault(case["category"], []).append(1 / first if first else 0.0)
            if case["category"] == "multi_source":
                multi_recalls.append(len(expected & set(files[:5])) / len(expected))
            if outdated := case.get("outdated_file"):
                rank_old = next((i for i, f in enumerate(files) if f == outdated), None)
                outdated_first.append(
                    rank_old is not None and (first is None or rank_old + 1 < first)
                )
            if mode == "hybrid_rerank" and first is None:
                failures.append(_failure(case, "retrieval_miss", f"top {k}: {files}"))
        n = len(scored)
        modes[mode] = {
            "n": n,
            "hit@1": hits[1] / n,
            "hit@3": hits[3] / n,
            "hit@5": hits[5] / n,
            "mrr": sum(reciprocal_ranks) / n,
            "multi_source_recall@5": _mean(multi_recalls),
            "outdated_ranked_first": _mean(outdated_first),
            "mrr_by_category": {cat: _mean(rr) for cat, rr in sorted(by_category.items())},
        }
        for case in tenant_checks:
            result = retrieve(
                session, user.workspace_id, case["question"], settings, mode=mode,
                apply_threshold=False, save_trace=False,
            )  # fmt: skip
            leaks += _count_leaks(session, user.workspace_id, result.candidates, case)
    return {
        "k": k,
        "modes": modes,
        "latency_ms_p50": _pct(retrieval_latency, 50),
        "latency_ms_p95": _pct(retrieval_latency, 95),
        "_leaks": leaks,
    }


def _search_text(settings: Settings, case: dict) -> str:
    """What the copilot would search for (follow-ups include the previous question)."""
    if settings.retrieval_follow_up_context:
        return search_query(case["question"], case.get("history", []))
    return case["question"]


def _count_leaks(session, workspace_id, chunks, case) -> int:
    ids = [c.chunk_id for c in chunks]
    foreign = 0
    if ids:
        foreign = session.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.id.in_(ids), Chunk.workspace_id != workspace_id)
        )
    forbidden = sum(c.filename in case.get("forbidden_files", []) for c in chunks)
    return foreign + forbidden


# --- Answers, tools, security ----------------------------------------------------------------


def _eval_answers(session, settings, cases, users, llm, failures, rows, judge=None):
    counts = Counter()
    answer_latency, tool_latency = [], []
    tool_calls = tool_ok = 0
    security = Counter()
    faithfulness: list[float] = []
    judge_errors = 0
    to_judge: list[tuple] = []  # judged after all answers: one model swap, not one per case
    for case in cases:
        if case["category"] in ("unauthorized_action",) or case.get("expect_http_status"):
            continue
        user = users[case.get("user", DEFAULT_USER)]
        customer = _customer(session, user, case.get("customer"))
        case_settings = settings
        if fault := case.get("crm_fault"):
            case_settings = settings.model_copy(update={"crm_fault": fault, "crm_max_retries": 1})

        conversation_id = None  # follow-up cases: replay the earlier turns first
        for earlier in case.get("history", []):
            conversation_id = ask(
                session, case_settings, user, earlier, customer=customer, llm=llm
            ).conversation.id
        started = time.perf_counter()
        run = ask(
            session, case_settings, user, case["question"], customer=customer, llm=llm,
            conversation_id=conversation_id,
        )  # fmt: skip
        answer_latency.append(int((time.perf_counter() - started) * 1000))

        text = run.payload.answer.lower()
        cited_files = [
            c.filename
            for i, c in enumerate(run.retrieval.chunks)
            if source_id(i) in run.payload.citations
        ]
        source_files = [c.filename for c in run.retrieval.chunks]
        expected = set(case.get("expected_files", []))
        row = {
            "case_id": case["id"],
            "category": case["category"],
            "mode": run.mode,
            "abstained": run.payload.abstained,
            "cited_files": "|".join(cited_files),
            "tool_calls": "|".join(f"{c.tool_name}:{c.status}" for c in run.tool_ctx.calls),
            "proposed_action": run.payload.proposed_action.type,
            "latency_ms": answer_latency[-1],
            "faithfulness": "",
            "checks_failed": "",
        }

        # Defined and called within this iteration, so the loop variables are current.
        def check(metric: str, passed: bool, detail: str = "") -> None:
            counts[f"{metric}_n"] += 1
            counts[f"{metric}_pass"] += passed
            if not passed:
                failures.append(_failure(case, metric, detail or run.payload.answer[:200]))  # noqa: B023
                row["checks_failed"] += metric + ";"  # noqa: B023

        if case.get("expect_abstain"):
            check("correct_abstention", run.payload.abstained)
        elif expected:
            check("answered_when_answerable", not run.payload.abstained)
        if not run.payload.abstained and expected:
            check("citation_coverage", bool(cited_files))
            if cited_files:
                check(
                    "citation_correctness",
                    all(f in expected for f in cited_files),
                    f"cited {cited_files}, expected {sorted(expected)}",
                )
        if case.get("must_include") and not run.payload.abstained:
            missing = [s for s in case["must_include"] if s.lower() not in text]
            check("required_facts", not missing, f"missing {missing}")
        if case.get("must_not_include"):
            found = [s for s in case["must_not_include"] if s.lower() in text]
            check("no_forbidden_claims", not found, f"contains {found}")
            if found and case["category"] == "injection":
                security["injection_followed"] += 1
        if tool := case.get("expect_tool"):
            used = any(c.tool_name == tool and c.status == "ok" for c in run.tool_ctx.calls)
            if run.mode == "offline" and tool == "get_recent_tickets":
                used = any(
                    c.status == "ok" for c in run.tool_ctx.calls
                )  # offline reads status only
            check("account_tool_used", used, f"calls: {row['tool_calls']}")
        if status := case.get("expect_tool_status"):
            statuses = [c.status for c in run.tool_ctx.calls]
            check("tool_fault_handled", bool(statuses) and statuses[0] == status, f"{statuses}")
        if judge and run.mode == "llm" and not run.payload.abstained:
            context = {source_id(i): c.content for i, c in enumerate(run.retrieval.chunks)}
            tool_ids = tool_source_ids(run.tool_ctx.calls)
            for call in run.tool_ctx.calls:
                if call.id in tool_ids:
                    context[tool_ids[call.id]] = json.dumps(call.result)
            to_judge.append((case, row, run.payload.answer, context))
        forbidden_actions = case.get("forbid_action_types", [])
        if run.payload.proposed_action.type in forbidden_actions:
            security["injection_followed"] += 1
            failures.append(
                _failure(case, "forbidden_action_proposed", run.payload.proposed_action.type)
            )
        if case.get("forbidden_files"):
            security["cross_tenant_leaks"] += sum(
                f in case["forbidden_files"] for f in source_files
            )

        selected = customer.external_id if customer else None
        for call in run.tool_ctx.calls:
            if call.status == "ok" and call.arguments.get("customer_id") != selected:
                security["unauthorized_tool_successes"] += 1
            if not case.get("crm_fault"):
                tool_calls += 1
                tool_ok += call.status == "ok"
                tool_latency.append(call.latency_ms)
        rows.append(row)

    for case, row, answer, context in to_judge:
        verdict = judge_faithfulness(judge, answer, context)
        if verdict.score is None:
            judge_errors += verdict.error is not None
            continue
        faithfulness.append(verdict.score)
        row["faithfulness"] = round(verdict.score, 3)
        if verdict.unsupported:
            failures.append(
                _failure(case, "unsupported_claims", " | ".join(verdict.unsupported)[:400])
            )

    executed = session.scalar(
        select(func.count())
        .select_from(ProposedAction)
        .where(ProposedAction.status == ActionStatus.EXECUTED)
        .where(ProposedAction.decided_by.is_(None))
    )
    security["actions_executed_without_approval"] = executed

    def rate(metric: str) -> float | None:
        n = counts[f"{metric}_n"]
        return round(counts[f"{metric}_pass"] / n, 4) if n else None

    metrics = [
        "correct_abstention", "answered_when_answerable", "citation_coverage",
        "citation_correctness", "required_facts", "no_forbidden_claims", "account_tool_used",
        "tool_fault_handled",
    ]  # fmt: skip
    answers = {
        "mode": "llm" if llm else "offline",
        "n": len(rows),
        **{m: rate(m) for m in metrics},
        "checks": {m: counts[f"{m}_n"] for m in metrics},
        "faithfulness": round(statistics.fmean(faithfulness), 4) if faithfulness else None,
        "faithfulness_n": len(faithfulness) if judge else None,
        "judge_errors": judge_errors if judge else None,
        "note": None
        if llm
        else "Offline mode quotes retrieved evidence instead of generating text, so "
        "required_facts / no_forbidden_claims mostly measure retrieval, not an LLM.",
    }
    tools = {
        "calls": tool_calls,
        "success_rate": round(tool_ok / tool_calls, 4) if tool_calls else None,
        "latency_ms_p50": _pct(tool_latency, 50),
        "latency_ms_p95": _pct(tool_latency, 95),
    }
    latencies = {"answer_p50": _pct(answer_latency, 50), "answer_p95": _pct(answer_latency, 95)}
    security.setdefault("injection_followed", 0)
    security.setdefault("unauthorized_tool_successes", 0)
    security.setdefault("cross_tenant_leaks", 0)
    return answers, tools, dict(security), latencies


def _eval_http(session, settings, cases, users, failures) -> dict:
    """Role and tenant checks through the real API (same code path as the UI)."""
    agent = users[DEFAULT_USER]
    brightpath = _customer(session, agent, "CUST-1001")
    action = propose_action(
        session, workspace_id=agent.workspace_id, customer_id=brightpath.id, proposed_by=agent,
        ticket_external_id="TCK-2041", action_type="add_ticket_tag", value="eval-check",
    )  # fmt: skip
    session.commit()

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    allowed = 0
    checks = 0
    try:
        with TestClient(app) as client:
            for case in cases:
                expected = case.get("expect_http_status")
                if expected is None:
                    continue
                headers = {"X-User": case.get("user", DEFAULT_USER)}
                if case["category"] == "unauthorized_action":
                    response = client.post(
                        f"/api/actions/{action.id}/approve", headers=headers, json={}
                    )
                else:  # another tenant's customer
                    other = session.scalar(
                        select(Customer).where(Customer.external_id == case["customer"])
                    )
                    response = client.post(
                        "/api/copilot/query",
                        headers=headers,
                        json={"question": case["question"], "customer_id": str(other.id)},
                    )
                checks += 1
                if response.status_code != expected:
                    allowed += 1
                    failures.append(_failure(case, "http_status", f"got {response.status_code}"))
    finally:
        app.dependency_overrides.clear()
    session.refresh(action)
    return {
        "http_checks": checks,
        "unauthorized_requests_allowed": allowed,
        "unapproved_action_still_pending": action.status == ActionStatus.PENDING,
    }


# --- Helpers ---------------------------------------------------------------------------------


def _customer(session, user, external_id):
    if not external_id:
        return None
    return session.scalar(
        select(Customer).where(
            Customer.external_id == external_id, Customer.workspace_id == user.workspace_id
        )
    )


def _index_info(session, workspace_id) -> dict:
    current = (
        select(func.count())
        .select_from(Chunk)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .where(Chunk.workspace_id == workspace_id, DocumentVersion.is_current.is_(True))
    )
    documents = (
        select(func.count())
        .select_from(SourceDocument)
        .where(SourceDocument.workspace_id == workspace_id)
    )
    models = session.scalars(select(Chunk.embedding_model).distinct()).all()
    return {
        "documents": session.scalar(documents),
        "chunks": session.scalar(current),
        "embedding_models": models,
    }


def _failure(case: dict, metric: str, detail: str) -> dict:
    return {"case_id": case["id"], "category": case["category"], "metric": metric, "detail": detail}


def _mean(values: list) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _pct(values: list[int], p: int) -> int | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return int(statistics.quantiles(values, n=100, method="inclusive")[p - 1])


def _git_commit() -> str | None:
    """HEAD, plus "-dirty" when tracked files have uncommitted changes (results are only
    reproducible from a clean commit)."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=HERE, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no", "--", ".", ":!evals/results"],
            cwd=HERE.parent, text=True, stderr=subprocess.DEVNULL,
        ).strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return None
    return f"{commit}-dirty" if dirty else commit


def print_summary(report: dict) -> None:
    print(f"\nRun {report['run_id']}  ({report['dataset']['cases']} cases, "
          f"answers: {report['answers']['mode']})")  # fmt: skip
    print("\nRetrieval        hit@1  hit@3  hit@5   MRR   multi-recall@5  outdated-first")
    for mode, m in report["retrieval"]["modes"].items():
        print(
            f"  {mode:<14} {m['hit@1']:.2f}   {m['hit@3']:.2f}   {m['hit@5']:.2f}   "
            f"{m['mrr']:.2f}   {m['multi_source_recall@5'] or 0:.2f}            "
            f"{m['outdated_ranked_first'] or 0:.2f}"
        )
    print("\nAnswers")
    for key, value in report["answers"].items():
        if isinstance(value, float):
            print(f"  {key:<26} {value:.2f}")
    print("\nSecurity", json.dumps(report["security"]))
    print("Tools   ", json.dumps(report["tools"]))
    print("Latency ", json.dumps(report["latency_ms"]))
    print(f"Failures: {len(report['failures'])} (see report)")


if __name__ == "__main__":
    sys.exit(main())
