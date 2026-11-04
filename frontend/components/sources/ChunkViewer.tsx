"use client";

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
    return <EmptyState title="No chunks">This version has not been indexed yet.</EmptyState>;
  }

  const tokens = data.reduce((sum, c) => sum + c.token_count, 0);
  return (
    <div className="space-y-3">
      <p className="text-[12px] text-ink-3">
        {data.length} chunks · {tokens} tokens · embedded with{" "}
        <span className="font-mono">{data[0].embedding_model ?? "—"}</span>
      </p>
      {data.map((c) => {
        const page = pageLabel(c.page_start, c.page_end);
        return (
          <div key={c.id} className="rounded-lg border border-line" data-testid="chunk">
            <div className="flex flex-wrap items-center gap-2 border-b border-line bg-paper px-3 py-2 text-[12px]">
              <span className="font-mono text-ink-4">#{c.chunk_index}</span>
              <span className="font-medium text-ink">
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
            </div>
            <pre className="max-h-72 overflow-auto p-3 font-sans text-[12px] leading-relaxed whitespace-pre-wrap text-ink-2">
              {c.content}
            </pre>
          </div>
        );
      })}
    </div>
  );
}
