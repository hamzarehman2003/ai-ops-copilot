"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { SearchResult } from "@/lib/api";
import { formatScore, pageLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

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
  const heading = result.heading_path.join(" › ");

  return (
    <Card
      size={compact ? "sm" : "default"}
      className="animate-rise rounded-lg border shadow-card ring-0"
      data-testid="search-result"
    >
      <CardHeader className="flex items-start gap-3">
        <span
          className={cn(
            "numeric mt-0.5 shrink-0 leading-none font-semibold",
            rank === 1 ? "text-primary" : "text-muted-foreground/70",
            compact ? "text-ui" : "text-[15px]",
          )}
        >
          {rank}
        </span>
        <div className="min-w-0 flex-1">
          <div
            className="truncate text-body font-medium text-foreground"
            title={result.document_title}
          >
            {result.document_title}
          </div>
          <div className="truncate text-meta text-muted-foreground" title={heading}>
            {heading || "(no heading)"}
          </div>
          <div className="mt-0.5 truncate font-mono text-micro text-muted-foreground/70">
            {result.filename} · v{result.version_number}
            {page ? ` · ${page}` : ""}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <dl
          className={cn(
            "flex overflow-hidden rounded-md border text-center",
            compact ? "text-micro" : "text-caption",
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
          className={cn(
            "mt-3 leading-relaxed whitespace-pre-wrap text-foreground/80",
            compact ? "text-meta" : "text-body",
          )}
        >
          {text}
        </p>
        {long && (
          <button
            type="button"
            className="mt-1.5 text-meta font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            onClick={() => setExpanded((x) => !x)}
          >
            {expanded ? "Show less" : "Show full chunk"}
          </button>
        )}
      </CardContent>
    </Card>
  );
}

function Score({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="min-w-0 flex-1 border-l px-1 py-1.5 first:border-l-0">
      <dt className="text-[0.92em] tracking-[0.08em] text-muted-foreground uppercase">{label}</dt>
      <dd
        className={cn(
          "numeric",
          strong ? "font-medium text-foreground" : "text-foreground/80",
        )}
      >
        {value}
      </dd>
    </div>
  );
}
