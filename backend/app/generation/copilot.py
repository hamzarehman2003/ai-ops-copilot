"""The copilot: question -> retrieval -> (LLM + read-only tools) -> checked answer.

Code, not the model, owns every rule that matters:
- retrieval is scoped to the caller's workspace inside the query;
- tools only see the customer the human selected (checked in tools/registry.py);
- citations are checked against what was actually retrieved ([S#] = a document) or returned
  by a tool in this run ([T#] = a successful tool result); an answer with no valid citation is
  turned into an abstention ("cite or abstain");
- a proposed action is validated and stored as `pending`; nothing is executed here.

Without an API key the copilot runs in *offline* mode: the same retrieval and tools, but the
"answer" is the best evidence, quoted and cited, with no generation.
"""

import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.generation.llm import LLM, LLMError
from app.generation.prompts import (
    ANSWER_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
    source_id,
    tool_source_id,
)
from app.generation.query_rewrite import is_weak, merge, rewrite_queries
from app.models import Conversation, Customer, Message, ToolCall, ToolCallStatus, User
from app.retrieval.query import search_query
from app.retrieval.reranker import relevance
from app.retrieval.search import RetrievalResult, RetrievedChunk, retrieve
from app.tools.actions import ActionError, payload_value, propose_action
from app.tools.registry import READ_TOOLS, ToolContext, run_tool

CITATION = re.compile(r"\[([ST]\d+)\]")
Progress = Callable[[dict], None]  # receives {"step": ..., ...} as the run advances (UI only)
HISTORY_MESSAGES = 6
NO_EVIDENCE = (
    "I couldn't find enough evidence in the knowledge base or the account tools to answer "
    "this reliably."
)


class ProposedActionOut(BaseModel):
    type: str
    ticket_id: str
    value: str
    reason: str


class EvidenceItem(BaseModel):
    source_id: str
    fact: str


class AnswerPayload(BaseModel):
    evidence: list[EvidenceItem] = []  # what the model relied on (stored, not shown inline)
    answer: str
    citations: list[str]
    abstained: bool
    missing_information: str = ""
    proposed_action: ProposedActionOut


@dataclass
class CopilotRun:
    conversation: Conversation
    message: Message
    retrieval: RetrievalResult
    tool_ctx: ToolContext
    payload: AnswerPayload
    mode: str
    model: str | None
    warnings: list[str] = field(default_factory=list)
    action_id: uuid.UUID | None = None
    action_error: str | None = None
    latency_ms: int = 0


def ask(
    session: Session,
    settings: Settings,
    user: User,
    question: str,
    *,
    customer: Customer | None = None,
    conversation_id: uuid.UUID | None = None,
    llm: LLM | None = None,
    retrieval_mode: str | None = None,
    on_progress: Progress | None = None,
) -> CopilotRun:
    """Answer one question. The caller has already checked that `customer` is in the user's
    workspace; this function re-scopes everything to user.workspace_id anyway.

    `on_progress` only reports what is happening (for a live UI); it never changes the run."""
    emit = on_progress or (lambda event: None)
    started = time.perf_counter()
    workspace_id = user.workspace_id
    conversation, history = _conversation(session, user, customer, conversation_id)

    session.add(
        Message(
            workspace_id=workspace_id,
            conversation_id=conversation.id,
            role="user",
            content=question,
        )
    )
    message = Message(
        workspace_id=workspace_id, conversation_id=conversation.id, role="assistant", content=""
    )
    session.add(message)
    session.flush()  # ids for traces / tool calls

    emit({"step": "retrieving"})
    previous = [m["content"] for m in history if m["role"] == "user"]
    query = search_query(question, previous) if settings.retrieval_follow_up_context else question
    retrieval = retrieve(
        session, workspace_id, query, settings, mode=retrieval_mode, message_id=message.id
    )
    emit(_retrieved_event(retrieval))
    if (
        llm is not None
        and settings.query_rewrite
        and is_weak(retrieval, settings.query_rewrite_below_score)
    ):
        # Weak search (often a paraphrase): retry in the documentation's vocabulary.
        if rewrites := rewrite_queries(llm, query):
            emit({"step": "rewriting", "queries": rewrites})
            extra = [
                retrieve(session, workspace_id, q, settings, mode=retrieval_mode, save_trace=False)
                for q in rewrites
            ]
            retrieval = merge(retrieval, extra, settings.retrieval_k)
            emit(_retrieved_event(retrieval))
    ctx = ToolContext(
        session=session,
        settings=settings,
        workspace_id=workspace_id,
        allowed_customer_id=customer.id if customer else None,
        message_id=message.id,
    )
    warnings: list[str] = []

    payload, mode, model = None, "offline", None
    if llm is not None:
        # Never hold a transaction (and a pooled connection) while waiting on the network:
        # commit what we have (question, trace) before the model runs; tool rounds commit too.
        session.commit()
        try:
            payload, model = _run_llm(
                llm, settings, question, retrieval.chunks, customer, ctx, history, emit
            )
            mode = "llm"
        except LLMError as exc:
            warnings.append(f"The language model is unavailable ({exc}); showing evidence instead.")
            emit({"step": "llm_failed", "error": str(exc)})
    if payload is None:
        payload = _offline_answer(retrieval.chunks, customer, ctx, emit)

    emit({"step": "checking"})
    payload = _enforce_grounding(payload, retrieval.chunks, ctx, warnings)
    run = CopilotRun(conversation, message, retrieval, ctx, payload, mode, model, warnings)
    _maybe_propose(session, run, user, customer)

    run.latency_ms = int((time.perf_counter() - started) * 1000)
    message.content = payload.answer
    message.data = {
        "abstained": payload.abstained,
        "missing_information": payload.missing_information,
        "evidence": [e.model_dump() for e in payload.evidence],
        "citations": [
            _citation(c, i)
            for i, c in enumerate(retrieval.chunks)
            if source_id(i) in payload.citations
        ],
        "mode": mode,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "retrieval_mode": retrieval.mode,
        "rewritten_queries": retrieval.params.get("rewritten_queries", []),
        "retrieval_trace_id": str(retrieval.trace_id),
        "proposed_action_id": str(run.action_id) if run.action_id else None,
        "action_error": run.action_error,
        "warnings": warnings,
        "latency_ms": run.latency_ms,
    }
    session.commit()
    return run


# --- LLM path ------------------------------------------------------------------------------


def _run_llm(
    llm: LLM,
    settings: Settings,
    question: str,
    chunks: list[RetrievedChunk],
    customer: Customer | None,
    ctx: ToolContext,
    history: list[dict],
    emit: Progress,
) -> tuple[AnswerPayload, str]:
    label = f"{customer.external_id} ({customer.name})" if customer else None
    messages = [
        *history,
        {"role": "user", "content": build_user_prompt(question, chunks, label)},
    ]
    tools = [spec.api_definition() for spec in READ_TOOLS.values()] if customer else []

    for round_number in range(settings.llm_max_tool_rounds + 1):
        emit({"step": "model", "round": round_number + 1, "model": llm.model})
        turn = llm.turn(
            system=SYSTEM_PROMPT, messages=messages, tools=tools, output_schema=ANSWER_SCHEMA
        )
        if turn.stop_reason == "refusal":
            return _abstain("The model declined to answer this request."), turn.model
        if turn.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": turn.content})
            continue
        if turn.tool_uses:
            if round_number == settings.llm_max_tool_rounds:
                break
            messages.append({"role": "assistant", "content": turn.content})
            results = []
            for tool_use in turn.tool_uses:  # all results go back in ONE user message
                outcome = _run_tool(ctx, tool_use.name, tool_use.input, emit)
                content = outcome.for_model()
                if outcome.ok:  # citable as [T#], like documents are [S#]
                    sid = tool_source_ids(ctx.calls)[outcome.record.id]
                    content = json.dumps({"source_id": sid, **outcome.result})
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": content,
                        "is_error": not outcome.ok,
                    }
                )
            messages.append({"role": "user", "content": results})
            ctx.session.commit()  # tool-call records, before the next (slow) model turn
            continue
        try:
            return AnswerPayload.model_validate(json.loads(turn.text)), turn.model
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError(f"Unparseable answer ({turn.stop_reason})") from exc
    raise LLMError("Too many tool rounds")


# --- Offline path (no LLM) -------------------------------------------------------------------


def _offline_answer(
    chunks: list[RetrievedChunk], customer: Customer | None, ctx: ToolContext, emit: Progress
) -> AnswerPayload:
    lines, cited = [], []
    if customer is not None:
        outcome = _run_tool(ctx, "get_account_status", {"customer_id": customer.external_id}, emit)
        if outcome.ok:
            a = outcome.result
            sid = tool_source_ids(ctx.calls)[outcome.record.id]
            lines.append(
                f"Account (from CRM): {a['name']} is on the {a['plan']} plan, status "
                f"{a['account_status']}, {a['seats_used']}/{a['seats_paid']} seats used"
                + (f". Billing note: {a['billing_note'].rstrip('.')}" if a["billing_note"] else "")
                + f". [{sid}]"
            )
            cited.append(sid)
        else:
            lines.append(f"Account status unavailable (tool error: {outcome.error_code}).")

    for i, chunk in enumerate(chunks[:3]):
        heading = " > ".join(chunk.heading_path) or chunk.document_title
        lines.append(f"{heading}: {_snippet(chunk.content, 320)} [{source_id(i)}]")
        cited.append(source_id(i))

    if not cited:
        return _abstain("No relevant documentation was found for this question.")
    header = "The most relevant evidence from the knowledge base:"
    return AnswerPayload(
        answer="\n\n".join([header, *lines]),
        citations=cited,
        abstained=False,
        proposed_action=ProposedActionOut(type="none", ticket_id="", value="", reason=""),
    )


# --- Checks applied to every answer ------------------------------------------------------------


def _enforce_grounding(
    payload: AnswerPayload,
    chunks: list[RetrievedChunk],
    ctx: ToolContext,
    warnings: list[str],
) -> AnswerPayload:
    known = {source_id(i) for i in range(len(chunks))} | set(tool_source_ids(ctx.calls).values())
    claimed = set(payload.citations) | set(CITATION.findall(payload.answer))
    invalid = claimed - known
    if invalid:
        warnings.append(f"Removed citations to unknown sources: {sorted(invalid)}")
        # Also from the text, so the UI never shows a marker that points nowhere.
        payload.answer = CITATION.sub(
            lambda m: "" if m.group(1) in invalid else m.group(0), payload.answer
        )
        payload.answer = re.sub(r"[ \t]+([.,;:!?])", r"\1", payload.answer)
        payload.answer = re.sub(r"(?<=\S)[ \t]{2,}", " ", payload.answer).strip()
    valid = sorted(claimed & known, key=lambda s: (s[0], int(s[1:])))
    payload.citations = valid

    # A successful tool call alone is not evidence: the answer must cite it ([T#]) or a
    # document ([S#]), so a policy answer can't ride on an unrelated account lookup.
    if not payload.abstained and not valid:
        warnings.append("Answer had no valid citation or tool evidence; converted to abstention.")
        return _abstain(payload.missing_information or "No supporting evidence was cited.")
    return payload


def _maybe_propose(
    session: Session, run: CopilotRun, user: User, customer: Customer | None
) -> None:
    proposal = run.payload.proposed_action
    if proposal.type == "none" or run.payload.abstained:  # no evidence, no action
        return
    try:
        action = propose_action(
            session,
            workspace_id=user.workspace_id,
            customer_id=customer.id if customer else None,
            proposed_by=user,
            ticket_external_id=proposal.ticket_id,
            action_type=proposal.type,
            value=proposal.value,
            reason=proposal.reason,
            message_id=run.message.id,
        )
        run.action_id = action.id
    except ActionError as exc:  # invalid proposals are dropped, and we say why
        run.action_error = exc.detail
        run.warnings.append(f"Proposed action rejected by policy: {exc.detail}")


def _abstain(reason: str) -> AnswerPayload:
    return AnswerPayload(
        answer=NO_EVIDENCE,
        citations=[],
        abstained=True,
        missing_information=reason,
        proposed_action=ProposedActionOut(type="none", ticket_id="", value="", reason=""),
    )


# --- Helpers ---------------------------------------------------------------------------------


def _run_tool(ctx: ToolContext, name: str, arguments: dict, emit: Progress):
    emit({"step": "tool", "name": name})
    outcome = run_tool(ctx, name, arguments)
    emit({"step": "tool_done", "name": name, "ok": outcome.ok, "error": outcome.error_code})
    return outcome


def _conversation(
    session: Session,
    user: User,
    customer: Customer | None,
    conversation_id: uuid.UUID | None,
) -> tuple[Conversation, list[dict]]:
    customer_id = customer.id if customer else None
    if conversation_id is not None:
        conversation = session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == user.workspace_id,
                Conversation.user_id == user.id,
            )
        )
        # Switching customers starts a new conversation: history never crosses customers.
        if conversation is not None and conversation.customer_id == customer_id:
            previous = session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.seq.desc())
                .limit(HISTORY_MESSAGES)
            ).all()
            # Source ids are per turn: [S2] in an old answer is a different chunk now, so
            # markers are dropped from history to stop the model reusing them.
            history = [
                {"role": m.role, "content": _without_markers(m.content)}
                for m in reversed(previous)
                if m.content
            ]
            return conversation, _well_formed(history)

    conversation = Conversation(
        workspace_id=user.workspace_id, user_id=user.id, customer_id=customer_id
    )
    session.add(conversation)
    session.flush()
    return conversation, []


def _well_formed(history: list[dict]) -> list[dict]:
    """The API needs user/assistant turns alternating and starting with a user turn."""
    while history and history[0]["role"] != "user":
        history.pop(0)
    while history and history[-1]["role"] != "assistant":
        history.pop()
    return history


def _retrieved_event(retrieval: RetrievalResult) -> dict:
    return {
        "step": "retrieved",
        "count": len(retrieval.chunks),
        "documents": list(dict.fromkeys(c.document_title for c in retrieval.chunks)),
        "latency_ms": retrieval.latency_ms,
    }


def _without_markers(text: str) -> str:
    text = re.sub(r"[ \t]*" + CITATION.pattern, "", text)
    return re.sub(r"[ \t]+([.,;:!?])", r"\1", text)


def _snippet(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _citation(chunk: RetrievedChunk, index: int) -> dict:
    return {
        "source_id": source_id(index),
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "document_title": chunk.document_title,
        "filename": chunk.filename,
        "version_number": chunk.version_number,
        "heading": " > ".join(chunk.heading_path),
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "snippet": _snippet(chunk.content, 400),
        "rerank_score": chunk.rerank_score,
        "relevance": None
        if chunk.rerank_score is None
        else round(relevance(chunk.rerank_score), 3),
    }


def citation_list(run: CopilotRun) -> list[dict]:
    return [
        _citation(c, i)
        for i, c in enumerate(run.retrieval.chunks)
        if source_id(i) in run.payload.citations
    ]


def tool_source_ids(calls: list[ToolCall]) -> dict[uuid.UUID, str]:
    """[T#] ids of a run's successful tool calls, in call order (failed attempts get none)."""
    ok = [c for c in calls if c.status == ToolCallStatus.OK]
    return {c.id: tool_source_id(i) for i, c in enumerate(ok)}


def source_list(run: CopilotRun) -> list[dict]:
    return [_citation(c, i) for i, c in enumerate(run.retrieval.chunks)]


def proposal_summary(run: CopilotRun) -> dict | None:
    p = run.payload.proposed_action
    if p.type == "none":
        return None
    return {
        "id": str(run.action_id) if run.action_id else None,
        "type": p.type,
        "ticket_id": p.ticket_id,
        "value": payload_value(p.type, {"note": p.value, "tag": p.value, "status": p.value}),
        "reason": p.reason,
        "error": run.action_error,
    }
