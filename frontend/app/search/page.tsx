"use client";

import { useState } from "react";
import { Icon } from "@/components/icons";
import { SearchResultCard } from "@/components/search/SearchResultCard";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupText,
} from "@/components/ui/input-group";
import {
  Button,
  EmptyState,
  ErrorBanner,
  PageHeader,
  Segmented,
  Spinner,
} from "@/components/ui";
import { api, SEARCH_MODES, type SearchMode, type SearchResponse } from "@/lib/api";
import { formatMs } from "@/lib/format";
import { cn } from "@/lib/utils";

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
        className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center"
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
      >
        <InputGroup className="h-10 flex-1 bg-card shadow-card">
          <InputGroupAddon className="pl-3">
            <Icon name="search" className="size-4" />
          </InputGroupAddon>
          <InputGroupInput
            aria-label="Query"
            data-testid="search-query"
            className="text-ui-lg"
            value={q}
            maxLength={500}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search the knowledge base…"
          />
          {q && (
            <InputGroupAddon align="inline-end">
              <InputGroupButton size="icon-xs" aria-label="Clear query" onClick={() => setQ("")}>
                <Icon name="close" className="size-3.5" />
              </InputGroupButton>
            </InputGroupAddon>
          )}
        </InputGroup>
        <div className="flex items-center gap-2">
          <InputGroup className="h-10 w-24 bg-card shadow-card" title="Results to return (1–20)">
            <InputGroupAddon className="pl-3">
              <InputGroupText className="eyebrow">k</InputGroupText>
            </InputGroupAddon>
            <InputGroupInput
              type="number"
              min={1}
              max={20}
              aria-label="k"
              className="numeric text-ui"
              value={k}
              onChange={(e) => setK(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            />
          </InputGroup>
          <Button
            type="submit"
            variant="primary"
            disabled={busy || !q.trim()}
            className="h-10 flex-1 px-4 sm:flex-none"
          >
            Search
          </Button>
        </div>
      </form>

      <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Segmented
            label="Retrieval mode"
            value={mode}
            onChange={setMode}
            options={SEARCH_MODES.map((m) => ({ value: m, label: MODE_LABELS[m] }))}
          />
          <span className="text-small text-muted-foreground">{MODE_NOTES[mode]}</span>
        </div>
        <Button onClick={() => void compareAll()} disabled={busy || !q.trim()}>
          <Icon name="layers" className="size-3.5" />
          Compare all four modes
        </Button>
      </div>

      {busy && (
        <div className="flex items-center gap-2.5 py-6 text-ui text-muted-foreground">
          <Spinner /> Searching…
        </div>
      )}

      {!busy && !single && !compare && (
        <EmptyState
          title="Run a query"
          icon="search"
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {SAMPLE_QUERIES.map((s) => (
                <Button
                  key={s}
                  size="sm"
                  className="font-mono text-meta"
                  onClick={() => {
                    setQ(s);
                    void search(s);
                  }}
                >
                  {s}
                </Button>
              ))}
            </div>
          }
        >
          Dense finds paraphrases, lexical finds exact codes like{" "}
          <code className="font-mono text-foreground/80">SSO-401</code>, hybrid fuses both with RRF, and
          the reranker reorders the fused candidates. Try one:
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
    <section className={cn(compact && "min-w-0")} data-testid={`results-${outcome.mode}`}>
      <div className="mb-3 border-b pb-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-ui-lg font-semibold text-foreground">{MODE_LABELS[outcome.mode]}</h2>
          {r && (
            <span className="numeric text-caption text-muted-foreground">
              {r.results.length} · {formatMs(r.latency_ms)}
            </span>
          )}
        </div>
        <p className="text-meta text-muted-foreground">{MODE_NOTES[outcome.mode]}</p>
      </div>
      {outcome.error != null && <ErrorBanner error={outcome.error} />}
      {r?.results.length === 0 && (
        <EmptyState title="No results" compact>
          No chunks matched in this mode.
        </EmptyState>
      )}
      <div className={compact ? "space-y-2.5" : "space-y-3"}>
        {r?.results.map((res, i) => (
          <SearchResultCard key={res.chunk_id} rank={i + 1} result={res} compact={compact} />
        ))}
      </div>
    </section>
  );
}
