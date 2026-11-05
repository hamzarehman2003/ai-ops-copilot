import type { Citation } from "@/lib/api";
import { formatScore, pageLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge, Card, MeterBar } from "../ui";

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
    <Card
      id={citationDomId(messageId, citation.source_id)}
      data-testid="citation-card"
      className={cn(
        "border text-left transition-colors",
        highlighted && "border-primary/40 bg-primary/5",
        flash && "cite-flash",
      )}
    >
      <div className="flex min-w-0 items-start gap-2.5 px-3.5 pt-3">
        <Badge
          tone={highlighted ? "indigo" : "gray"}
          className={cn(
            "mt-px h-[18px] px-1.5 text-[10.5px] font-medium",
            highlighted && "border-primary bg-primary text-primary-foreground",
          )}
        >
          {citation.source_id}
        </Badge>
        <div className="min-w-0">
          <div className="truncate text-[13px] font-medium text-foreground">
            {citation.document_title}
          </div>
          {citation.heading && (
            <div className="truncate text-[12px] text-muted-foreground" title={citation.heading}>
              {citation.heading}
            </div>
          )}
        </div>
      </div>
      <p className="mx-3.5 mt-2 mb-3 line-clamp-4 text-[12.5px] leading-relaxed whitespace-pre-wrap text-foreground/80">
        {citation.snippet}
      </p>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 border-t bg-muted/40 px-3.5 py-2 font-mono text-[10.5px] text-muted-foreground">
        <span className="truncate">
          {citation.filename} · v{citation.version_number}
        </span>
        {page && <span>{page}</span>}
        {citation.rerank_score != null && (
          <span className="numeric">rerank {formatScore(citation.rerank_score)}</span>
        )}
        {citation.relevance != null && (
          <span className="ml-auto">
            <MeterBar
              value={citation.relevance}
              label={`Relevance (rerank score ${formatScore(citation.rerank_score)})`}
            />
          </span>
        )}
      </div>
    </Card>
  );
}
