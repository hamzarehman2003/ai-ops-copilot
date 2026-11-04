import type { Citation } from "@/lib/api";
import { formatScore, pageLabel } from "@/lib/format";
import { cx, MeterBar } from "../ui";

export function citationDomId(messageId: string, sourceId: string) {
  return `cite-${messageId}-${sourceId}`;
}

export function CitationCard({
  messageId,
  citation,
  highlighted,
  flash,
}: {
  messageId: string;
  citation: Citation;
  highlighted: boolean;
  flash: boolean;
}) {
  const page = pageLabel(citation.page_start, citation.page_end);
  return (
    <div
      id={citationDomId(messageId, citation.source_id)}
      data-testid="citation-card"
      className={cx(
        "rounded-xl border p-3.5 transition-colors",
        highlighted ? "border-accent/40 bg-accent-soft/40" : "border-line bg-paper/40",
        flash && "cite-flash",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <span
            className={cx(
              "mt-px rounded-[5px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium",
              highlighted ? "bg-accent text-white" : "bg-surface text-ink-2 ring-1 ring-line",
            )}
          >
            {citation.source_id}
          </span>
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium text-ink">
              {citation.document_title}
            </div>
            {citation.heading && (
              <div className="truncate text-[12px] text-ink-3" title={citation.heading}>
                {citation.heading}
              </div>
            )}
          </div>
        </div>
      </div>
      <p className="mt-2.5 line-clamp-4 text-[12.5px] leading-relaxed whitespace-pre-wrap text-ink-2">
        {citation.snippet}
      </p>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-[10.5px] text-ink-4">
        <span>
          {citation.filename} · v{citation.version_number}
        </span>
        {page && <span>{page}</span>}
        {citation.rerank_score != null && <span>rerank {formatScore(citation.rerank_score)}</span>}
        {citation.relevance != null && (
          <span className="ml-auto">
            <MeterBar
              value={citation.relevance}
              label={`Relevance (rerank score ${formatScore(citation.rerank_score)})`}
            />
          </span>
        )}
      </div>
    </div>
  );
}
