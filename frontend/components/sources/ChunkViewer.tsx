"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { api, type Chunk, type Source } from "@/lib/api";
import { pageLabel } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { Badge, Drawer, EmptyState, ErrorBanner, Loading } from "../ui";

/** Drawer listing the chunks of a document's current version. */
export function ChunkViewer({ source, onClose }: { source: Source | null; onClose: () => void }) {
  return (
    <Drawer
      open={source !== null}
      onClose={onClose}
      title={source ? `Chunks · ${source.title}` : "Chunks"}
      wide
    >
      {source && <ChunkList documentId={source.id} />}
    </Drawer>
  );
}

function ChunkList({ documentId }: { documentId: string }) {
  const { data, error, loading } = useAsync<Chunk[]>(() => api.chunks(documentId), [documentId]);
  if (loading) return <Loading />;
  if (error) return <ErrorBanner error={error} />;
  if (!data?.length) {
    return (
      <EmptyState title="No chunks" icon="layers">
        This version has not been indexed yet.
      </EmptyState>
    );
  }

  const tokens = data.reduce((sum, c) => sum + c.token_count, 0);
  return (
    <div className="space-y-3">
      <dl className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-muted-foreground">
        <div className="flex items-baseline gap-1.5">
          <dt className="eyebrow">Chunks</dt>
          <dd className="numeric text-foreground">{data.length}</dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <dt className="eyebrow">Tokens</dt>
          <dd className="numeric text-foreground">{tokens}</dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <dt className="eyebrow">Embedded with</dt>
          <dd className="font-mono text-foreground">{data[0].embedding_model ?? "—"}</dd>
        </div>
      </dl>
      {data.map((c) => {
        const page = pageLabel(c.page_start, c.page_end);
        return (
          <Card
            key={c.id}
            className="gap-0 rounded-lg border py-0 shadow-card ring-0"
            data-testid="chunk"
          >
            <CardHeader className="flex flex-wrap items-center gap-2 bg-muted/40 px-3 py-2 text-[12px]">
              <span className="numeric text-muted-foreground">#{c.chunk_index}</span>
              <span className="font-medium text-foreground">
                {c.heading_path.length ? c.heading_path.join(" › ") : "(no heading)"}
              </span>
              <span className="ml-auto flex flex-wrap gap-1.5">
                <Badge>{c.token_count} tokens</Badge>
                {page && <Badge>{page}</Badge>}
                <Badge>v{c.version_number}</Badge>
                {c.contains_table && <Badge tone="purple">table</Badge>}
                <Badge tone="gray" title="Character span in the parsed text">
                  chars {c.char_start}–{c.char_end}
                </Badge>
              </span>
            </CardHeader>
            <Separator />
            <CardContent className="p-0">
              <pre className="max-h-72 overflow-auto p-3 font-sans text-[12px] leading-relaxed whitespace-pre-wrap text-foreground/80">
                {c.content}
              </pre>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
