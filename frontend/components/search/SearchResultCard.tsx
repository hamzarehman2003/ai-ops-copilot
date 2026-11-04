"use client";

import { useState } from "react";
import type { SearchResult } from "@/lib/api";
import { formatScore, pageLabel } from "@/lib/format";
import { Card, cx } from "../ui";

const PREVIEW = 320;

export function SearchResultCard({
  rank,
  result,
  compact,
}: {
  rank: number;
  result: SearchResult;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const long = result.content.length > PREVIEW;
  const text = expanded || !long ? result.content : `${result.content.slice(0, PREVIEW)}…`;
  const page = pageLabel(result.page_start, result.page_end);

  return (
    <Card className={cx("animate-rise", compact ? "p-3.5" : "p-5")} data-testid="search-result">
      <div className="flex items-start gap-3">
        <span
          className={cx(
            "shrink-0 font-display leading-none tabular-nums",
            rank === 1 ? "text-accent" : "text-ink-4",
            compact ? "text-[1.35rem]" : "text-[1.75rem]",
          )}
        >
          {rank}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-medium text-ink" title={result.document_title}>
            {result.document_title}
          </div>
          <div className="truncate text-[12px] text-ink-3" title={result.heading_path.join(" › ")}>
            {result.heading_path.join(" › ") || "(no heading)"}
          </div>
          <div className="mt-0.5 truncate font-mono text-[10.5px] text-ink-4">
            {result.filename} · v{result.version_number}
            {page ? ` · ${page}` : ""}
          </div>
        </div>
      </div>
      <dl
        className={cx(
          "mt-3 grid grid-cols-4 overflow-hidden rounded-lg border border-line text-center",
          compact ? "text-[10.5px]" : "text-[11px]",
        )}
      >
        <Score label="dense" value={result.dense_rank != null ? `#${result.dense_rank}` : "—"} />
        <Score
          label="lexical"
          value={result.lexical_rank != null ? `#${result.lexical_rank}` : "—"}
        />
        <Score label="RRF" value={formatScore(result.rrf_score, 4)} />
        <Score label="rerank" value={formatScore(result.rerank_score)} strong />
      </dl>
      <p
        className={cx(
          "mt-3 leading-relaxed whitespace-pre-wrap",
          compact ? "text-[12px] text-ink-2" : "text-[13.5px] text-ink-2",
        )}
      >
        {text}
      </p>
      {long && (
        <button
          type="button"
          className="mt-1.5 text-[12px] font-medium text-ink-3 underline-offset-2 hover:text-ink hover:underline"
          onClick={() => setExpanded((x) => !x)}
        >
          {expanded ? "Show less" : "Show full chunk"}
        </button>
      )}
    </Card>
  );
}

function Score({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="border-l border-line px-1 py-1.5 first:border-l-0">
      <dt className="text-ink-4">{label}</dt>
      <dd className={cx("font-mono tabular-nums", strong ? "font-medium text-ink" : "text-ink-2")}>
        {value}
      </dd>
    </div>
  );
}
