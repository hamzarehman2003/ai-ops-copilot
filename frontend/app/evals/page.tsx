"use client";

import {
  humanize,
  isRecord,
  KeyValueTable,
  RecordTable,
  ReportValue,
} from "@/components/evals/ReportValue";
import { RetrievalComparison } from "@/components/evals/RetrievalComparison";
import { Icon } from "@/components/icons";
import { asModeMetrics, ModeChart, type ModeMetrics } from "@/components/overview/ModeChart";
import {
  Button,
  EmptyState,
  ErrorBanner,
  Loading,
  PageHeader,
  Panel,
  StatTile,
} from "@/components/ui";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api, ApiError, type EvalReport } from "@/lib/api";
import { formatDate, formatMs, pct } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";

// Keys with dedicated rendering; anything else in the report is shown generically at the end.
const KNOWN = ["run_id", "created_at", "versions", "dataset", "retrieval", "failures"];

const SECURITY_KEYS = [
  "cross_tenant_leaks",
  "actions_executed_without_approval",
  "injection_followed",
  "unauthorized_tool_successes",
  "unauthorized_requests_allowed",
];

export default function EvalsPage() {
  const report = useAsync<EvalReport>(() => api.latestEvaluation(), []);
  const notRun = report.error instanceof ApiError && report.error.status === 404;

  return (
    <div className="animate-rise">
      <PageHeader
        eyebrow="Governance"
        title="Evaluations"
        description="The latest run of evals/run_eval.py: retrieval per mode, answer quality, security and tool-fault checks. Every number here comes from that report."
        actions={
          <Button onClick={() => void report.reload()}>
            <Icon name="refresh" className="h-3.5 w-3.5" />
            Refresh
          </Button>
        }
      />
      {report.loading && !report.data ? (
        <Loading />
      ) : notRun ? (
        <EmptyState title="No evaluation has been run yet">
          Run <code className="font-mono text-foreground/80">python evals/run_eval.py</code> from the repo
          root, then refresh this page.
        </EmptyState>
      ) : report.error ? (
        <ErrorBanner error={report.error} />
      ) : report.data ? (
        <Report data={report.data} />
      ) : null}
    </div>
  );
}

function Report({ data }: { data: EvalReport }) {
  const dataset = isRecord(data.dataset) ? data.dataset : null;
  const retrieval = isRecord(data.retrieval) ? data.retrieval : null;
  const modes = retrieval && isRecord(retrieval.modes) ? retrieval.modes : null;
  const failures = Array.isArray(data.failures) ? data.failures : null;
  const rest = Object.entries(data).filter(([k]) => !KNOWN.includes(k));
  const versions = isRecord(data.versions) ? data.versions : null;
  const defaultMode =
    versions && isRecord(versions.retrieval) && typeof versions.retrieval.default_mode === "string"
      ? versions.retrieval.default_mode
      : "hybrid_rerank";
  const best = asModeMetrics(modes?.[defaultMode]);
  const security = isRecord(data.security) ? data.security : null;
  const incidents = security
    ? SECURITY_KEYS.reduce((s, k) => s + (typeof security[k] === "number" ? security[k] : 0), 0)
    : null;
  const p50 = typeof retrieval?.latency_ms_p50 === "number" ? retrieval.latency_ms_p50 : null;

  return (
    <div className="space-y-4" data-testid="eval-report">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11.5px] text-muted-foreground">
        {data.run_id != null && (
          <span>
            run <span className="text-foreground">{String(data.run_id)}</span>
          </span>
        )}
        {typeof data.created_at === "string" && <span>{formatDate(data.created_at)}</span>}
        {dataset?.cases != null && <span>{String(dataset.cases)} cases</span>}
        {versions?.git_commit != null && <span>commit {String(versions.git_commit)}</span>}
      </div>

      {best && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label="Hit@1 · default mode"
            value={pct(best["hit@1"])}
            unit="%"
            tone="success"
            note={`Correct document ranked first, ${defaultMode}`}
          />
          <StatTile label="MRR" value={best.mrr.toFixed(3)} note="Mean reciprocal rank, 1.0 = always first" />
          <StatTile
            label="Retrieval p50"
            value={p50 != null ? formatMs(p50).replace(/ (ms|s)$/, "") : "—"}
            unit={p50 != null ? (p50 >= 1000 ? "s" : "ms") : undefined}
            note="Embed, search, fuse and rerank, on CPU"
          />
          <StatTile
            label="Security incidents"
            tone={incidents === 0 ? "success" : incidents ? "danger" : "default"}
            value={incidents ?? "—"}
            note="Leaks, injections followed, unapproved writes"
          />
        </div>
      )}

      {retrieval && (
        <Panel
          eyebrow={retrieval.k != null ? `k = ${String(retrieval.k)}` : "Retrieval"}
          title="Retrieval by mode"
        >
          {modes ? (
            <>
              <ModeChart modes={modes as Record<string, ModeMetrics>} defaultMode={defaultMode} />
              <div className="mt-6 border-t pt-4">
                <RetrievalComparison modes={modes} />
              </div>
            </>
          ) : null}
          {Object.keys(retrieval).some((k) => k !== "k" && k !== "modes") && (
            <div className="mt-4">
              <KeyValueTable data={retrieval} omit={["k", "modes"]} />
            </div>
          )}
        </Panel>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {rest.map(([key, value]) => (
          <Panel key={key} title={humanize(key)}>
            {isRecord(value) ? (
              <KeyValueTable data={value} parentKey={key} />
            ) : (
              <ReportValue name={key} value={value} />
            )}
          </Panel>
        ))}
        {versions && (
          <Panel title="Versions">
            <KeyValueTable data={versions} />
          </Panel>
        )}
        {dataset && (
          <Panel title="Dataset">
            <KeyValueTable data={dataset} omit={["by_category"]} />
            {isRecord(dataset.by_category) && (
              <div className="mt-4">
                <div className="eyebrow mb-2">By category</div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(dataset.by_category).map(([name, count]) => (
                    <span
                      key={name}
                      className="rounded-sm border bg-muted/40 px-2 py-0.5 text-[12px] text-foreground/80"
                    >
                      {name.replace(/_/g, " ")}{" "}
                      <span className="numeric text-foreground">{String(count)}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Panel>
        )}
      </div>

      {failures && (
        <Panel eyebrow="Per-case misses" title={`Failures · ${failures.length}`}>
          {failures.length === 0 ? (
            <p className="text-[13px] text-success">No failing cases.</p>
          ) : failures.every(isRecord) ? (
            <ScrollArea className="max-h-[32rem] [&>[data-slot=scroll-area-viewport]]:max-h-[32rem] [&_[data-slot=scroll-area-viewport]>div]:block!">
              <RecordTable rows={failures} />
            </ScrollArea>
          ) : (
            <ReportValue name="failures" value={failures} />
          )}
        </Panel>
      )}
    </div>
  );
}
