"use client";

import { useState } from "react";
import { Icon } from "@/components/icons";
import { SearchResultCard } from "@/components/search/SearchResultCard";
import {
  Button,
  cx,
  EmptyState,
  ErrorBanner,
  PageHeader,
  Segmented,
  Spinner,
} from "@/components/ui";
import { api, SEARCH_MODES, type SearchMode, type SearchResponse } from "@/lib/api";
import { formatMs } from "@/lib/format";

const MODE_LABELS: Record<SearchMode, string> = {
  dense: "Dense",
  lexical: "Lexical",
  hybrid: "Hybrid",
  hybrid_rerank: "Hybrid + rerank",
};

const MODE_NOTES: Record<SearchMode, string> = {
  dense: "Vector similarity: finds paraphrases",
  lexical: "Postgres full-text: finds exact codes",
  hybrid: "Both, fused with RRF",
  hybrid_rerank: "RRF, then a cross-encoder reorders",
};

const SAMPLE_QUERIES = ["refund annual plan", "SSO-409", "API rate limit", "data retention"];

type Outcome = { mode: SearchMode; response?: SearchResponse; error?: unknown };

export default function SearchLabPage() {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid_rerank");
  const [k, setK] = useState(5);
  const [busy, setBusy] = useState(false);
  const [single, setSingle] = useState<Outcome | null>(null);
  const [compare, setCompare] = useState<Outcome[] | null>(null);

  const run = async (m: SearchMode, query = q): Promise<Outcome> => {
    try {
      return { mode: m, response: await api.search(query.trim(), m, k) };
    } catch (error) {
      return { mode: m, error };
    }
  };

  const search = async (query = q) => {
    if (!query.trim()) return;
    setBusy(true);
    setCompare(null);
    setSingle(await run(mode, query));
    setBusy(false);
  };

  const compareAll = async () => {
    if (!q.trim()) return;
    setBusy(true);
    setSingle(null);
    // Sequential so per-mode latencies aren't skewed by running concurrently.
    const out: Outcome[] = [];
    for (const m of SEARCH_MODES) out.push(await run(m));
    setCompare(out);
    setBusy(false);
  };

  return (
    <div className="animate-rise">
      <PageHeader
        eyebrow="Knowledge"
        title="Search lab"
        description="Retrieval without the LLM. See exactly which chunks each mode returns, and with what scores."
      />

      <form
        className="mb-4"
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
      >
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface py-2 pr-2 pl-5 shadow-card transition-[border-color,box-shadow] focus-within:border-ink-4 focus-within:shadow-pop">
          <Icon name="search" className="h-[18px] w-[18px] shrink-0 text-ink-3" />
          <input
            aria-label="Query"
            className="h-10 min-w-0 flex-1 bg-transparent text-[15px] text-ink placeholder:text-ink-4 focus:outline-none"
            data-testid="search-query"
            value={q}
            maxLength={500}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search the knowledge base…"
          />
          <label className="hidden items-center gap-2 border-l border-line pl-3 text-[12px] text-ink-3 sm:flex">
            k
            <input
              type="number"
              min={1}
              max={20}
              aria-label="k"
              className="h-8 w-12 rounded-md border border-line bg-paper px-2 text-center font-mono text-[12.5px] text-ink focus:border-ink-4 focus:outline-none"
              value={k}
              onChange={(e) => setK(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            />
          </label>
          <Button type="submit" variant="primary" disabled={busy || !q.trim()} className="h-10 rounded-xl">
            Search
          </Button>
        </div>
      </form>

      <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <Segmented
          label="Retrieval mode"
          value={mode}
          onChange={setMode}
          options={SEARCH_MODES.map((m) => ({ value: m, label: MODE_LABELS[m] }))}
        />
        <Button onClick={() => void compareAll()} disabled={busy || !q.trim()}>
          Compare all four modes
        </Button>
      </div>

      {busy && (
        <div className="flex items-center gap-2.5 py-6 text-[13px] text-ink-3">
          <Spinner /> Searching…
        </div>
      )}

      {!busy && !single && !compare && (
        <EmptyState title="Run a query">
          Dense finds paraphrases, lexical finds exact codes like{" "}
          <code className="font-mono text-ink-2">SSO-401</code>, hybrid fuses both with RRF, and
          the reranker reorders the fused candidates.
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            {SAMPLE_QUERIES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  setQ(s);
                  void search(s);
                }}
                className="rounded-full border border-line bg-surface px-3 py-1 font-mono text-[12px] text-ink-2 transition-colors hover:border-ink-4 hover:text-ink"
              >
                {s}
              </button>
            ))}
          </div>
        </EmptyState>
      )}

      {single && !busy && (
        <div className="max-w-4xl">
          <ModeResults outcome={single} />
        </div>
      )}

      {compare && !busy && (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {compare.map((o) => (
            <ModeResults key={o.mode} outcome={o} compact />
          ))}
        </div>
      )}
    </div>
  );
}

function ModeResults({ outcome, compact }: { outcome: Outcome; compact?: boolean }) {
  const r = outcome.response;
  return (
    <section className={cx(compact && "min-w-0")} data-testid={`results-${outcome.mode}`}>
      <div className="mb-3 border-b border-line pb-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-[14px] font-semibold text-ink">{MODE_LABELS[outcome.mode]}</h2>
          {r && (
            <span className="font-mono text-[11.5px] text-ink-3">
              {r.results.length} · {formatMs(r.latency_ms)}
            </span>
          )}
        </div>
        <p className="text-[12px] text-ink-3">{MODE_NOTES[outcome.mode]}</p>
      </div>
      {outcome.error != null && <ErrorBanner error={outcome.error} />}
      {r?.results.length === 0 && <EmptyState title="No results" />}
      <div className={compact ? "space-y-2.5" : "space-y-3"}>
        {r?.results.map((res, i) => (
          <SearchResultCard key={res.chunk_id} rank={i + 1} result={res} compact={compact} />
        ))}
      </div>
    </section>
  );
}
