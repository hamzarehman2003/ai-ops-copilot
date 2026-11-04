"use client";

import { useEffect, useState } from "react";
import { FileGlyph } from "@/components/FileGlyph";
import { Icon } from "@/components/icons";
import { ChunkViewer } from "@/components/sources/ChunkViewer";
import { UploadForm } from "@/components/sources/UploadForm";
import {
  Button,
  Card,
  cx,
  EmptyState,
  ErrorBanner,
  Loading,
  PageHeader,
  Spinner,
  StatusBadge,
} from "@/components/ui";
import { useRole } from "@/components/UserProvider";
import { api, type Source } from "@/lib/api";
import { formatBytes, timeAgo } from "@/lib/format";
import { canUpload } from "@/lib/roles";
import { useAsync } from "@/lib/useAsync";

const POLL_MS = 2000;
const th = "eyebrow px-5 py-3 font-medium";

export default function SourcesPage() {
  const role = useRole();
  const sources = useAsync<Source[]>(() => api.sources(), []);
  const [viewing, setViewing] = useState<Source | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [reindexing, setReindexing] = useState<string | null>(null);

  const list = sources.data ?? [];
  const busy = list.some((s) =>
    ["pending", "processing"].includes(s.latest_version?.status ?? ""),
  );
  const { reload } = sources;

  // Processing happens in the background: poll while anything is pending/processing.
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => void reload(true), POLL_MS);
    return () => clearInterval(t);
  }, [busy, reload]);

  const toggleDeprecated = async (s: Source) => {
    setActionError(null);
    try {
      await api.setDeprecated(s.id, !s.deprecated);
      await reload(true);
    } catch (e) {
      setActionError(e);
    }
  };

  const reindex = async (s: Source) => {
    setReindexing(s.id);
    setActionError(null);
    try {
      await api.reindex(s.id);
      await reload(true);
    } catch (e) {
      setActionError(e);
    } finally {
      setReindexing(null);
    }
  };

  const ready = list.filter((s) => s.latest_version?.status === "ready").length;
  const deprecated = list.filter((s) => s.deprecated).length;
  const bytes = list.reduce((sum, s) => sum + (s.latest_version?.file_size_bytes ?? 0), 0);

  return (
    <div className="animate-rise">
      <PageHeader
        eyebrow="Knowledge"
        title="Sources"
        description="Everything the copilot can cite. Uploads are parsed, chunked, embedded and swapped in atomically once indexing succeeds."
        actions={
          <>
            {busy && (
              <span className="flex items-center gap-2 text-[12.5px] text-ink-3">
                <Spinner className="h-3 w-3" /> Indexing, refreshing every 2 s
              </span>
            )}
            <Button onClick={() => void reload()}>
              <Icon name="refresh" className="h-3.5 w-3.5" />
              Refresh
            </Button>
          </>
        }
      />

      {list.length > 0 && (
        <dl className="mb-6 flex flex-wrap gap-x-10 gap-y-3 border-y border-line py-4">
          <Fact label="Documents" value={list.length} />
          <Fact label="Ready" value={ready} />
          <Fact label="Deprecated" value={deprecated} />
          <Fact label="On disk" value={formatBytes(bytes)} />
        </dl>
      )}

      {canUpload(role) ? (
        <UploadForm onUploaded={() => void reload(true)} />
      ) : (
        role && (
          <p className="mb-5 flex items-center gap-2 text-[12.5px] text-ink-3">
            <Icon name="info" className="h-3.5 w-3.5" />
            Only admins can upload, reindex or deprecate sources. You are signed in as {role}.
          </p>
        )
      )}

      <div className="mb-3 empty:hidden">
        <ErrorBanner error={actionError} onDismiss={() => setActionError(null)} />
      </div>

      {sources.loading && !sources.data ? (
        <Loading />
      ) : sources.error ? (
        <ErrorBanner error={sources.error} />
      ) : list.length === 0 ? (
        <EmptyState title="No sources yet">
          Upload a PDF, Markdown, HTML or text file, or run{" "}
          <code className="font-mono">scripts.upload_demo_docs</code>.
        </EmptyState>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-left text-[13px]" data-testid="sources-table">
            <thead className="border-b border-line">
              <tr>
                <th className={th}>Document</th>
                <th className={th}>Version</th>
                <th className={th}>Status</th>
                <th className={cx(th, "text-right")}>Size</th>
                <th className={th}>Indexed</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {list.map((s) => {
                const v = s.latest_version;
                return (
                  <tr
                    key={s.id}
                    className="group align-middle transition-colors hover:bg-paper/60"
                    data-testid="source-row"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <FileGlyph type={s.source_type} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span
                              className={cx(
                                "font-medium",
                                s.deprecated ? "text-ink-3 line-through decoration-ink-4" : "text-ink",
                              )}
                            >
                              {s.title}
                            </span>
                            {s.deprecated && (
                              <span
                                className="rounded border border-line px-1 font-mono text-[10px] tracking-wide text-ink-3 uppercase"
                                title="Excluded from retrieval"
                              >
                                deprecated
                              </span>
                            )}
                          </div>
                          <div className="font-mono text-[11px] text-ink-4">{s.filename}</div>
                          {v?.error_message && (
                            <div className="mt-1 text-[12px] text-bad">{v.error_message}</div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-[12px] whitespace-nowrap text-ink-2">
                      {v ? `v${v.version_number}` : "—"}
                      {v && !v.is_current && (
                        <span className="ml-1.5 font-sans text-[11.5px] text-ink-4">not current</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">{v ? <StatusBadge status={v.status} /> : "—"}</td>
                    <td className="px-5 py-3.5 text-right font-mono text-[12px] whitespace-nowrap text-ink-3 tabular-nums">
                      {v ? formatBytes(v.file_size_bytes) : "—"}
                    </td>
                    <td className="px-5 py-3.5 text-[12.5px] whitespace-nowrap text-ink-3">
                      {timeAgo(v?.processed_at)}
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" onClick={() => setViewing(s)}>
                          Chunks
                        </Button>
                        {canUpload(role) && (
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={reindexing === s.id}
                            onClick={() => reindex(s)}
                          >
                            {reindexing === s.id ? "Reindexing…" : "Reindex"}
                          </Button>
                        )}
                        {canUpload(role) && (
                          <Button size="sm" variant="ghost" onClick={() => toggleDeprecated(s)}>
                            {s.deprecated ? "Restore" : "Deprecate"}
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      <ChunkViewer source={viewing} onClose={() => setViewing(null)} />
    </div>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="eyebrow">{label}</dt>
      <dd className="mt-1 font-display text-[1.75rem] leading-none text-ink tabular-nums">{value}</dd>
    </div>
  );
}
