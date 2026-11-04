"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { FileGlyph } from "@/components/FileGlyph";
import { Icon } from "@/components/icons";
import { ModeChart, type ModeMetrics } from "@/components/overview/ModeChart";
import { cx, Panel, StatTile, StatusBadge } from "@/components/ui";
import { useUser } from "@/components/UserProvider";
import { api, type Action, type AuditEvent, type EvalReport, type Meta, type Source } from "@/lib/api";
import { formatMs, pct, timeAgo } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";

type Rec = Record<string, unknown>;
const rec = (v: unknown): Rec | null =>
  typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Rec) : null;
const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

const ANSWER_METRICS: [string, string][] = [
  ["answered_when_answerable", "Answers when the docs cover it"],
  ["citation_coverage", "Answers that cite a source"],
  ["citation_correctness", "Cites the expected document"],
  ["required_facts", "Contains the required facts"],
  ["no_forbidden_claims", "Avoids outdated claims"],
  ["correct_abstention", "Abstains when it should"],
];

const SECURITY_KEYS = [
  "cross_tenant_leaks",
  "actions_executed_without_approval",
  "injection_followed",
  "unauthorized_tool_successes",
  "unauthorized_requests_allowed",
];

function greeting(d = new Date()) {
  const h = d.getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function OverviewPage() {
  const { me } = useUser();
  const meta = useAsync<Meta>(() => api.meta(), []);
  const sources = useAsync<Source[]>(() => api.sources(), []);
  const actions = useAsync<Action[]>(() => api.actions(), []);
  const audit = useAsync<AuditEvent[]>(() => api.auditEvents(7), []);
  const report = useAsync<EvalReport>(() => api.latestEvaluation(), []);

  const docs = sources.data ?? [];
  const ready = docs.filter((s) => s.latest_version?.status === "ready").length;
  const deprecated = docs.filter((s) => s.deprecated).length;
  const pending = (actions.data ?? []).filter((a) => a.status === "pending").length;
  const executed = (actions.data ?? []).filter((a) => a.status === "executed").length;

  const r = report.data;
  const retrieval = rec(r?.retrieval);
  const modes = rec(retrieval?.modes) as Record<string, ModeMetrics> | null;
  const versions = rec(r?.versions);
  const defaultMode = String(rec(versions?.retrieval)?.default_mode ?? "hybrid_rerank");
  const best = modes?.[defaultMode];
  const answers = rec(r?.answers);
  const security = rec(r?.security);
  const latency = rec(r?.latency_ms);
  const incidents = security
    ? SECURITY_KEYS.reduce((sum, k) => sum + (num(security[k]) ?? 0), 0)
    : null;
  const adversarial = rec(rec(r?.dataset)?.by_category);
  const adversarialCases = adversarial
    ? ["cross_tenant", "injection", "unauthorized_action", "tool_fault"].reduce(
        (s, k) => s + (num(adversarial[k]) ?? 0),
        0,
      )
    : null;

  const firstName = me?.user.name.split(" ")[0];
  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="animate-rise">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="eyebrow mb-2.5">{today}</div>
          <h1 className="font-display text-[2.6rem] leading-[1.02] tracking-[-0.02em] text-ink sm:text-[3.1rem]">
            {greeting()}
            {firstName ? (
              <>
                , <span className="italic">{firstName}</span>
              </>
            ) : null}
            <span className="text-accent">.</span>
          </h1>
          <p className="mt-3 max-w-xl text-[14.5px] leading-relaxed text-ink-3">
            The knowledge base, the approval queue and the latest evaluation run for{" "}
            <span className="text-ink-2">{me?.workspace.name ?? "your workspace"}</span>.
          </p>
        </div>
      </header>

      <AskBar />

      <section className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Key numbers">
        <StatTile
          label="Documents indexed"
          loading={sources.loading && !sources.data}
          value={ready}
          unit={`/ ${docs.length}`}
          note={
            <>
              {meta.data?.index.current_chunks ?? "—"} chunks in the index
              {deprecated > 0 && ` · ${deprecated} deprecated`}
            </>
          }
        />
        <StatTile
          label="Awaiting approval"
          accent={pending > 0}
          loading={actions.loading && !actions.data}
          value={pending}
          unit={pending === 1 ? "action" : "actions"}
          note={
            <Link href="/actions" className="inline-flex items-center gap-1 hover:text-ink">
              {executed} executed so far <Icon name="arrowRight" className="h-3 w-3" />
            </Link>
          }
        />
        <StatTile
          label="Top-1 retrieval accuracy"
          loading={report.loading && !report.data}
          value={best ? pct(best["hit@1"]) : "—"}
          unit={best ? "%" : undefined}
          note={
            best
              ? `MRR ${best.mrr.toFixed(3)} · ${String(best.n)} labelled questions`
              : "Run evals/run_eval.py"
          }
        />
        <StatTile
          label="Security incidents"
          loading={report.loading && !report.data}
          value={incidents ?? "—"}
          note={
            incidents == null
              ? "No evaluation yet"
              : `Leaks, injections and unapproved writes across ${adversarialCases ?? "—"} adversarial cases`
          }
        />
      </section>

      <section className="mt-4 grid gap-4 lg:grid-cols-3">
        <Panel
          className="lg:col-span-2"
          eyebrow={r?.run_id ? `Eval run ${String(r.run_id)}` : "Evaluation"}
          title="Retrieval quality by mode"
          actions={
            <Link
              href="/evals"
              className="inline-flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink"
            >
              Full report <Icon name="arrowUpRight" className="h-3.5 w-3.5" />
            </Link>
          }
        >
          {modes ? (
            <ModeChart modes={modes} defaultMode={defaultMode} />
          ) : (
            <Placeholder loading={report.loading}>
              No evaluation report yet. Run <code className="font-mono">evals/run_eval.py</code>.
            </Placeholder>
          )}
        </Panel>

        <Panel eyebrow="How an answer is built" title="Retrieval pipeline">
          <Pipeline meta={meta.data} />
        </Panel>
      </section>

      <section className="mt-4 grid gap-4 lg:grid-cols-3">
        <Panel
          eyebrow={answers?.mode ? `${String(answers.mode)} answers` : "Answers"}
          title="Answer quality"
        >
          {answers ? (
            <ul className="space-y-3.5">
              {ANSWER_METRICS.filter(([k]) => num(answers[k]) != null).map(([k, label]) => {
                const v = num(answers[k]) ?? 0;
                return (
                  <li key={k}>
                    <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[12.5px]">
                      <span className="text-ink-2">{label}</span>
                      <span className="font-mono text-ink tabular-nums">{pct(v, 0)}%</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-paper-2">
                      <div
                        className="h-full rounded-r-[4px] bg-ink"
                        style={{ width: `${v * 100}%` }}
                      />
                    </div>
                  </li>
                );
              })}
              {latency && (
                <li className="flex items-center justify-between border-t border-line pt-3 text-[12.5px]">
                  <span className="text-ink-3">Median end-to-end latency</span>
                  <span className="font-mono text-ink">{formatMs(num(latency.answer_p50))}</span>
                </li>
              )}
            </ul>
          ) : (
            <Placeholder loading={report.loading}>No answer metrics yet.</Placeholder>
          )}
        </Panel>

        <Panel
          eyebrow="Audit log"
          title="Recent activity"
          actions={
            <Link
              href="/audit"
              className="inline-flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink"
            >
              All <Icon name="arrowUpRight" className="h-3.5 w-3.5" />
            </Link>
          }
        >
          {audit.data?.length ? (
            <ol className="relative space-y-4 before:absolute before:top-1.5 before:bottom-1.5 before:left-[3.5px] before:w-px before:bg-line">
              {audit.data.map((e) => (
                <li key={e.id} className="relative pl-5">
                  <span
                    className={cx(
                      "absolute top-1.5 left-0 h-2 w-2 rounded-full ring-[3px] ring-surface",
                      /fail|reject|denied/.test(e.event_type) ? "bg-bad" : e.event_type.startsWith("action.") ? "bg-accent" : "bg-ink-4",
                    )}
                  />
                  <div className="text-[13px] leading-snug text-ink">{describeEvent(e)}</div>
                  <div className="mt-0.5 text-[11.5px] text-ink-3">
                    {e.actor_name ?? "System"} · {timeAgo(e.created_at)}
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <Placeholder loading={audit.loading}>Nothing has happened yet.</Placeholder>
          )}
        </Panel>

        <Panel
          eyebrow={`${docs.length} documents`}
          title="Knowledge base"
          actions={
            <Link
              href="/sources"
              className="inline-flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink"
            >
              Manage <Icon name="arrowUpRight" className="h-3.5 w-3.5" />
            </Link>
          }
          bodyClassName="px-2 pb-2"
        >
          {docs.length ? (
            <ul>
              {docs.slice(0, 7).map((s) => (
                <li
                  key={s.id}
                  className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-paper"
                >
                  <FileGlyph type={s.source_type} />
                  <div className="min-w-0 flex-1">
                    <div
                      className={cx(
                        "truncate text-[13px] text-ink",
                        s.deprecated && "text-ink-3 line-through decoration-ink-4",
                      )}
                    >
                      {s.title}
                    </div>
                    <div className="truncate font-mono text-[11px] text-ink-4">{s.filename}</div>
                  </div>
                  {s.latest_version && <StatusBadge status={s.latest_version.status} />}
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-3">
              <Placeholder loading={sources.loading}>No documents uploaded yet.</Placeholder>
            </div>
          )}
        </Panel>
      </section>
    </div>
  );
}

function AskBar() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const go = () => {
    const text = q.trim();
    router.push(text ? `/copilot?q=${encodeURIComponent(text)}` : "/copilot");
  };
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        go();
      }}
      className="group flex items-center gap-3 rounded-2xl border border-line bg-surface py-2 pr-2 pl-5 shadow-card transition-[border-color,box-shadow] focus-within:border-ink-4 focus-within:shadow-pop"
    >
      <Icon name="chat" className="h-[18px] w-[18px] shrink-0 text-ink-3" />
      <input
        aria-label="Ask the copilot"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Ask the copilot about a policy, an error code, or a customer…"
        className="h-10 min-w-0 flex-1 bg-transparent text-[15px] text-ink placeholder:text-ink-4 focus:outline-none"
      />
      <button
        type="submit"
        className="inline-flex h-10 items-center gap-2 rounded-xl bg-ink px-4 text-[13.5px] font-medium text-paper transition-colors hover:bg-ink-2"
      >
        Ask <Icon name="arrowRight" className="h-4 w-4" />
      </button>
    </form>
  );
}

function Pipeline({ meta }: { meta?: Meta }) {
  const shortModel = (m?: string | null) => (m ? m.split("/").pop() : "—");
  const steps: { title: string; detail: ReactNode }[] = [
    {
      title: "Recall",
      detail: (
        <>
          Dense ({shortModel(meta?.embedding_model)}) and Postgres full-text, top{" "}
          {meta?.retrieval.candidates ?? "—"} each
        </>
      ),
    },
    { title: "Fuse", detail: <>Reciprocal rank fusion, k = {meta?.retrieval.rrf_k ?? "—"}</> },
    { title: "Rerank", detail: <>Cross-encoder {shortModel(meta?.reranker_model)}</> },
    {
      title: "Gate",
      detail: (
        <>
          Keep top {meta?.retrieval.k ?? "—"} above score{" "}
          {meta?.retrieval.min_rerank_score ?? "—"}, else abstain
        </>
      ),
    },
    {
      title: "Answer",
      detail: meta?.llm.enabled ? (
        <>{meta.llm.model} with cited sources and read-only tools</>
      ) : (
        <>Offline: quotes the evidence with citations</>
      ),
    },
  ];
  return (
    <ol className="space-y-0">
      {steps.map((s, i) => (
        <li key={s.title} className="relative flex gap-3.5 pb-4 last:pb-0">
          {i < steps.length - 1 && (
            <span className="absolute top-7 bottom-0 left-[13px] w-px bg-line" aria-hidden />
          )}
          <span
            className={cx(
              "relative flex h-[27px] w-[27px] shrink-0 items-center justify-center rounded-full border font-mono text-[11px]",
              i === steps.length - 1
                ? "border-ink bg-ink text-paper"
                : "border-line-strong bg-surface text-ink-2",
            )}
          >
            {i + 1}
          </span>
          <div className="pt-0.5">
            <div className="text-[13px] font-medium text-ink">{s.title}</div>
            <div className="text-[12.5px] leading-snug text-ink-3">{s.detail}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function Placeholder({ loading, children }: { loading?: boolean; children: ReactNode }) {
  return loading ? (
    <div className="space-y-2.5 py-2">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-3 animate-pulse rounded bg-paper-2" style={{ width: `${90 - i * 18}%` }} />
      ))}
    </div>
  ) : (
    <p className="py-4 text-[13px] text-ink-3">{children}</p>
  );
}

const ACTION_VERBS: Record<string, string> = {
  "action.proposed": "Proposed",
  "action.approved": "Approved",
  "action.rejected": "Rejected",
  "action.executed": "Executed",
  "action.failed": "Failed to run",
};

function describeEvent(e: AuditEvent): string {
  const d = e.data ?? {};
  const file = typeof d.document === "string" ? d.document : typeof d.filename === "string" ? d.filename : null;
  switch (e.event_type) {
    case "source.indexed":
      return `Indexed ${file ?? "a document"}${d.version != null ? ` v${String(d.version)}` : ""}${d.chunks != null ? `, ${String(d.chunks)} chunk${d.chunks === 1 ? "" : "s"}` : ""}`;
    case "source.uploaded":
      return `Uploaded ${file ?? "a document"}`;
    case "source.deprecated":
      return `Deprecated ${file ?? "a document"}`;
    case "source.restored":
      return `Restored ${file ?? "a document"}`;
  }
  if (e.event_type in ACTION_VERBS) {
    const what = typeof d.action_type === "string" ? d.action_type.replace(/_/g, " ") : "an action";
    return `${ACTION_VERBS[e.event_type]} ${what}`;
  }
  const verb = e.event_type.replace(/[._]/g, " ");
  return verb.charAt(0).toUpperCase() + verb.slice(1);
}
