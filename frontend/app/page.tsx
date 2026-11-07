"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { FileGlyph } from "@/components/FileGlyph";
import { Button as ShadButton } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Icon, type IconName } from "@/components/icons";
import { asModeMetrics, ModeChart, type ModeMetrics } from "@/components/overview/ModeChart";
import {
  EmptyState,
  ErrorBanner,
  PageHeader,
  Panel,
  StatTile,
  StatusBadge,
} from "@/components/ui";
import { useUser } from "@/components/UserProvider";
import {
  api,
  type Action,
  type AuditEvent,
  type EvalReport,
  type Meta,
  type Source,
} from "@/lib/api";
import { formatMs, pct, timeAgo } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { cn } from "@/lib/utils";

type Rec = Record<string, unknown>;
const rec = (v: unknown): Rec | null =>
  typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Rec) : null;
const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

const ANSWER_METRICS: [string, string][] = [
  ["faithfulness", "Claims supported by the sources (LLM judge)"],
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
  const audit = useAsync<AuditEvent[]>(() => api.auditEvents(6), []);
  const report = useAsync<EvalReport>(() => api.latestEvaluation(), []);

  const docs = sources.data ?? [];
  const ready = docs.filter((s) => s.latest_version?.status === "ready").length;
  const deprecated = docs.filter((s) => s.deprecated).length;
  const allActions = actions.data ?? [];
  const pendingActions = allActions.filter((a) => a.status === "pending");
  const executed = allActions.filter((a) => a.status === "executed").length;

  const r = report.data;
  const retrieval = rec(r?.retrieval);
  const modes = rec(retrieval?.modes) as Record<string, ModeMetrics> | null;
  const versions = rec(r?.versions);
  const defaultMode = String(rec(versions?.retrieval)?.default_mode ?? "hybrid_rerank");
  const best = asModeMetrics(modes?.[defaultMode]);
  // The eval report is optional (404 before the first run); everything else should load.
  const loadError = [sources, actions, meta, audit].find((x) => x.error != null)?.error;
  const answers = rec(r?.answers);
  const security = rec(r?.security);
  const latency = rec(r?.latency_ms);
  const incidents = security
    ? SECURITY_KEYS.reduce((sum, k) => sum + (num(security[k]) ?? 0), 0)
    : null;
  const byCategory = rec(rec(r?.dataset)?.by_category);
  const adversarialCases = byCategory
    ? ["cross_tenant", "injection", "unauthorized_action", "tool_fault"].reduce(
        (s, k) => s + (num(byCategory[k]) ?? 0),
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
    <div>
      <PageHeader
        eyebrow={today}
        title={`${greeting()}${firstName ? `, ${firstName}` : ""}`}
        description={
          <>
            The knowledge base, the approval queue and the latest evaluation run for{" "}
            {me?.workspace.name ?? "your workspace"}.
          </>
        }
        actions={
          <>
            <LinkButton href="/sources" variant="secondary" icon="upload">
              Add source
            </LinkButton>
            <LinkButton href="/copilot" icon="chat">
              Open copilot
            </LinkButton>
          </>
        }
      />

      <AskBar />

      {loadError != null && (
        <div className="mt-4">
          <ErrorBanner error={loadError} />
        </div>
      )}

      <section className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Key numbers">
        <StatTile
          label="Documents indexed"
          loading={sources.loading && !sources.data}
          value={ready}
          unit={`of ${docs.length}`}
          note={
            <>
              {meta.data?.index.current_chunks ?? "—"} chunks searchable
              {deprecated > 0 && ` · ${deprecated} deprecated`}
            </>
          }
        />
        <StatTile
          label="Waiting for a decision"
          tone={pendingActions.length > 0 ? "warning" : "default"}
          loading={actions.loading && !actions.data}
          value={pendingActions.length}
          note={`${executed} executed after approval`}
        />
        <StatTile
          label="Top-1 retrieval accuracy"
          tone="success"
          loading={report.loading && !report.data}
          value={best ? pct(best["hit@1"]) : "—"}
          unit={best ? "%" : undefined}
          note={
            best ? `MRR ${best.mrr.toFixed(3)} on ${String(best.n)} questions` : "No evaluation yet"
          }
        />
        <StatTile
          label="Security incidents"
          tone={incidents == null ? "default" : incidents === 0 ? "success" : "danger"}
          loading={report.loading && !report.data}
          value={incidents ?? "—"}
          note={
            incidents == null
              ? "No evaluation yet"
              : `Across ${adversarialCases ?? "—"} adversarial test cases`
          }
        />
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel
          eyebrow="Latest evaluation"
          title="Retrieval quality by mode"
          footer={
            r ? (
              <span className="numeric text-meta">
                run {String(r.run_id)} · p50 {formatMs(num(retrieval?.latency_ms_p50))} per search
              </span>
            ) : undefined
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

      <Panel
        className="mt-6"
        eyebrow="Oldest first"
        title="Needs your decision"
        footer={
          <span className="ml-auto">
            <FooterLink href="/actions">Open approvals</FooterLink>
          </span>
        }
      >
        {pendingActions.length === 0 ? (
          <EmptyState icon="inbox" title="Nothing waiting" compact>
            When the copilot proposes a ticket note, tag or status change, it waits here until
            someone approves or rejects it.
          </EmptyState>
        ) : (
          <ul className="-mx-2 divide-y divide-border/70">
            {[...pendingActions]
              .reverse()
              .slice(0, 5)
              .map((a) => (
                <li key={a.id}>
                  <Link
                    href="/actions"
                    className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md px-2 py-3 transition-colors hover:bg-muted/60"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-foreground">{a.customer}</span>
                      <span className="numeric block text-meta text-muted-foreground">
                        {a.ticket} · {timeAgo(a.created_at)}
                      </span>
                    </span>
                    <span className="hidden min-w-0 flex-1 truncate text-body text-foreground/80 md:block">
                      {a.value}
                    </span>
                    <StatusBadge status={a.status} />
                  </Link>
                </li>
              ))}
          </ul>
        )}
      </Panel>

      <section className="mt-6 grid gap-6 lg:grid-cols-3">
        <Panel
          eyebrow="Latest evaluation"
          title="Answer quality"
          footer={
            latency ? (
              <span className="numeric text-meta">
                median answer {formatMs(num(latency.answer_p50))}
              </span>
            ) : undefined
          }
        >
          {answers ? (
            <ul className="space-y-3.5">
              {ANSWER_METRICS.filter(([k]) => num(answers[k]) != null).map(([k, label]) => {
                const v = num(answers[k]) ?? 0;
                return (
                  <li key={k}>
                    <div className="mb-1.5 flex items-baseline justify-between gap-3 text-ui">
                      <span className="text-foreground/80">{label}</span>
                      <span className="numeric text-foreground">{pct(v, 0)}%</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${v * 100}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <Placeholder loading={report.loading}>No answer metrics yet.</Placeholder>
          )}
        </Panel>

        <Panel
          eyebrow="Audit log"
          title="Recent activity"
          footer={
            <span className="ml-auto">
              <FooterLink href="/audit">View all</FooterLink>
            </span>
          }
        >
          {audit.data?.length ? (
            <ol className="relative space-y-4 before:absolute before:top-1.5 before:bottom-1.5 before:left-[3.5px] before:w-px before:bg-border">
              {audit.data.map((e) => (
                <li key={e.id} className="relative pl-5">
                  <span
                    className={cn(
                      "absolute top-1.5 left-0 h-2 w-2 rounded-full ring-[3px] ring-card",
                      /fail|reject|denied/.test(e.event_type)
                        ? "bg-destructive"
                        : e.event_type.startsWith("action.")
                          ? "bg-warning"
                          : "bg-primary",
                    )}
                  />
                  <div className="text-body leading-snug text-foreground">{describeEvent(e)}</div>
                  <div className="mt-0.5 text-meta text-muted-foreground">
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
          bodyClassName="px-3 pb-3"
          footer={
            <span className="ml-auto">
              <FooterLink href="/sources">Manage sources</FooterLink>
            </span>
          }
        >
          {docs.length ? (
            <ul>
              {docs.slice(0, 6).map((s) => (
                <li
                  key={s.id}
                  className="flex items-center gap-3 rounded-md px-2 py-2 transition-colors hover:bg-muted/60"
                >
                  <FileGlyph type={s.source_type} />
                  <div className="min-w-0 flex-1">
                    <div
                      className={cn(
                        "truncate text-body text-foreground",
                        s.deprecated && "text-muted-foreground line-through decoration-muted-foreground/60",
                      )}
                    >
                      {s.title}
                    </div>
                    <div className="truncate font-mono text-caption text-muted-foreground/60">{s.filename}</div>
                  </div>
                  {s.latest_version && <StatusBadge status={s.latest_version.status} />}
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-2">
              <Placeholder loading={sources.loading}>No documents uploaded yet.</Placeholder>
            </div>
          )}
        </Panel>
      </section>
    </div>
  );
}

function LinkButton({
  href,
  icon,
  variant = "primary",
  children,
}: {
  href: string;
  icon: IconName;
  variant?: "primary" | "secondary";
  children: ReactNode;
}) {
  return (
    <ShadButton
      asChild
      size="lg"
      variant={variant === "primary" ? "default" : "outline"}
      className={cn(
        "px-3.5",
        variant === "primary" ? "shadow-[inset_0_1px_0_rgb(255_255_255/0.14)]" : "bg-card shadow-card",
      )}
    >
      <Link href={href}>
        <Icon name={icon} />
        {children}
      </Link>
    </ShadButton>
  );
}

function FooterLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <ShadButton asChild variant="ghost" size="sm">
      <Link href={href}>
        {children} <Icon name="arrowRight" />
      </Link>
    </ShadButton>
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
    // action/name make it work even before hydration: a native submit lands on /copilot?q=...
    <form
      action="/copilot"
      onSubmit={(e) => {
        e.preventDefault();
        go();
      }}
    >
      <InputGroup className="h-12 bg-card shadow-card">
        <InputGroupAddon className="pl-4">
          <Icon name="chat" />
        </InputGroupAddon>
        <InputGroupInput
          aria-label="Ask the copilot"
          name="q"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask the copilot about a policy, an error code, or a customer…"
          className="text-ui-lg"
        />
        <InputGroupAddon align="inline-end" className="pr-1.5">
          <ShadButton type="submit" size="lg" className="px-3.5">
            Ask <Icon name="arrowRight" />
          </ShadButton>
        </InputGroupAddon>
      </InputGroup>
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
          Keep top {meta?.retrieval.k ?? "—"} above score {meta?.retrieval.min_rerank_score ?? "—"},
          else abstain
        </>
      ),
    },
    {
      title: "Answer",
      detail: meta?.llm.enabled ? (
        <>{meta.llm.model} with cited sources and read-only tools</>
      ) : (
        <>Quotes the most relevant evidence, with citations</>
      ),
    },
  ];
  return (
    <ol>
      {steps.map((s, i) => (
        <li key={s.title} className="relative flex gap-3.5 pb-4 last:pb-0">
          {i < steps.length - 1 && (
            <span className="absolute top-7 bottom-0 left-[13px] w-px bg-border" aria-hidden />
          )}
          <span
            className={cn(
              "numeric relative flex h-[27px] w-[27px] shrink-0 items-center justify-center rounded-full border text-caption",
              i === steps.length - 1
                ? "border-primary bg-primary text-primary-foreground"
                : "border-input bg-card text-foreground/80",
            )}
          >
            {i + 1}
          </span>
          <div className="pt-0.5">
            <div className="text-ui-lg font-medium text-foreground">{s.title}</div>
            <div className="text-ui leading-snug text-muted-foreground">{s.detail}</div>
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
        <div
          key={i}
          className="h-3 animate-pulse rounded bg-muted"
          style={{ width: `${90 - i * 18}%` }}
        />
      ))}
    </div>
  ) : (
    <p className="py-4 text-ui text-muted-foreground">{children}</p>
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
  const file =
    typeof d.document === "string"
      ? d.document
      : typeof d.filename === "string"
        ? d.filename
        : null;
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
