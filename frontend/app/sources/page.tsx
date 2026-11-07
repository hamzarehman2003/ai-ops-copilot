"use client";

import { MoreHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { FileGlyph } from "@/components/FileGlyph";
import { Icon } from "@/components/icons";
import { ChunkViewer } from "@/components/sources/ChunkViewer";
import { UploadForm } from "@/components/sources/UploadForm";
import { Button as ShadButton } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Button,
  EmptyState,
  ErrorBanner,
  Loading,
  PageHeader,
  Spinner,
  StatTile,
  StatusBadge,
} from "@/components/ui";
import { useRole } from "@/components/UserProvider";
import { api, errorMessage, type Source } from "@/lib/api";
import { formatBytes, timeAgo } from "@/lib/format";
import { canUpload } from "@/lib/roles";
import { useAsync } from "@/lib/useAsync";
import { cn } from "@/lib/utils";

const POLL_MS = 2000;
const th = "h-9 px-4 text-micro font-medium tracking-[0.1em] text-muted-foreground uppercase";
const td = "px-4 py-3";

type Filter = "all" | "ready" | "processing" | "deprecated";

const isProcessing = (s: Source) =>
  ["pending", "processing"].includes(s.latest_version?.status ?? "");
const isReady = (s: Source) => s.latest_version?.status === "ready";

const FILTERS: { value: Filter; label: string; test: (s: Source) => boolean }[] = [
  { value: "all", label: "All", test: () => true },
  { value: "ready", label: "Ready", test: isReady },
  { value: "processing", label: "Processing", test: isProcessing },
  { value: "deprecated", label: "Deprecated", test: (s) => s.deprecated },
];

export default function SourcesPage() {
  const role = useRole();
  const admin = canUpload(role);
  const sources = useAsync<Source[]>(() => api.sources(), []);
  const [viewing, setViewing] = useState<Source | null>(null);
  const [reindexing, setReindexing] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const list = useMemo(() => sources.data ?? [], [sources.data]);
  const busy = list.some(isProcessing);
  const { reload } = sources;

  // Processing happens in the background: poll while anything is pending/processing.
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => void reload(true), POLL_MS);
    return () => clearInterval(t);
  }, [busy, reload]);

  const toggleDeprecated = async (s: Source) => {
    const next = !s.deprecated;
    try {
      await api.setDeprecated(s.id, next);
      await reload(true);
      toast.success(next ? `Deprecated "${s.title}"` : `Restored "${s.title}"`, {
        description: next
          ? "Excluded from retrieval; kept for history."
          : "Back in retrieval results.",
      });
    } catch (e) {
      toast.error(next ? "Could not deprecate" : "Could not restore", {
        description: errorMessage(e),
      });
    }
  };

  const reindex = async (s: Source) => {
    setReindexing(s.id);
    try {
      await api.reindex(s.id);
      await reload(true);
      toast.success(`Reindexing "${s.title}"`, {
        description: "Processing in the background; the current version stays live until it finishes.",
      });
    } catch (e) {
      toast.error("Could not reindex", { description: errorMessage(e) });
    } finally {
      setReindexing(null);
    }
  };

  const ready = list.filter(isReady).length;
  const deprecated = list.filter((s) => s.deprecated).length;
  const bytes = list.reduce((sum, s) => sum + (s.latest_version?.file_size_bytes ?? 0), 0);

  const needle = query.trim().toLowerCase();
  const active = FILTERS.find((f) => f.value === filter) ?? FILTERS[0];
  const visible = list.filter(
    (s) =>
      active.test(s) &&
      (!needle ||
        s.title.toLowerCase().includes(needle) ||
        s.filename.toLowerCase().includes(needle)),
  );

  return (
    <div className="animate-rise">
      <PageHeader
        eyebrow="Knowledge"
        title="Sources"
        description="Everything the copilot can cite. Uploads are parsed, chunked, embedded and swapped in atomically once indexing succeeds."
        actions={
          <>
            {busy && (
              <span className="flex items-center gap-2 text-small text-muted-foreground">
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
        <section className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Totals">
          <StatTile label="Documents" value={list.length} note="Current versions" />
          <StatTile
            label="Ready to cite"
            value={ready}
            tone={ready === list.length ? "success" : "warning"}
            note={ready === list.length ? "Everything is indexed" : "Some are still indexing"}
          />
          <StatTile label="Deprecated" value={deprecated} note="Excluded from retrieval" />
          <StatTile label="On disk" value={formatBytes(bytes)} note="Original files" />
        </section>
      )}

      {admin ? (
        <UploadForm onUploaded={() => void reload(true)} />
      ) : (
        role && (
          <p className="mb-5 flex items-center gap-2 text-small text-muted-foreground">
            <Icon name="info" className="h-3.5 w-3.5" />
            Only admins can upload, reindex or deprecate sources. You are signed in as {role}.
          </p>
        )
      )}

      {sources.loading && !sources.data ? (
        <Loading />
      ) : sources.error ? (
        <ErrorBanner error={sources.error} />
      ) : list.length === 0 ? (
        <EmptyState title="No sources yet" icon="files">
          Upload a PDF, Markdown, HTML or text file to give the copilot something to cite.
        </EmptyState>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b">
            <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)} className="gap-0">
              <TabsList variant="line" className="h-10 gap-5 p-0" aria-label="Filter sources">
                {FILTERS.map((f) => (
                  <TabsTrigger key={f.value} value={f.value} className="h-full flex-none px-0.5 text-body after:bottom-[-1px]!">
                    {f.label}
                    <span className="numeric text-caption text-muted-foreground">
                      {list.filter(f.test).length}
                    </span>
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <InputGroup className="mb-2 h-8 w-full bg-card shadow-card sm:w-72">
              <InputGroupAddon>
                <Icon name="search" className="size-4" />
              </InputGroupAddon>
              <InputGroupInput
                aria-label="Filter by title or filename"
                placeholder="Filter by title or filename…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="text-ui"
              />
              {query && (
                <InputGroupAddon align="inline-end">
                  <button
                    type="button"
                    aria-label="Clear filter"
                    onClick={() => setQuery("")}
                    className="rounded p-0.5 text-muted-foreground hover:text-foreground"
                  >
                    <Icon name="close" className="size-3.5" />
                  </button>
                </InputGroupAddon>
              )}
            </InputGroup>
          </div>

          <div className="overflow-hidden rounded-lg border bg-card shadow-card">
            <Table className="text-ui" data-testid="sources-table">
              <TableHeader className="bg-muted/40">
                <TableRow className="hover:bg-transparent">
                  <TableHead className={th}>Document</TableHead>
                  <TableHead className={th}>Version</TableHead>
                  <TableHead className={th}>Status</TableHead>
                  <TableHead className={cn(th, "text-right")}>Size</TableHead>
                  <TableHead className={th}>Indexed</TableHead>
                  <TableHead className={cn(th, "w-0")}>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.length === 0 && (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                      No sources match this filter.
                    </TableCell>
                  </TableRow>
                )}
                {visible.map((s) => {
                  const v = s.latest_version;
                  return (
                    <TableRow key={s.id} data-testid="source-row">
                      <TableCell className={cn(td, "min-w-64 whitespace-normal")}>
                        <div className="flex items-center gap-3">
                          <FileGlyph type={s.source_type} />
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span
                                className={cn(
                                  "font-medium",
                                  s.deprecated
                                    ? "text-muted-foreground line-through decoration-muted-foreground/60"
                                    : "text-foreground",
                                )}
                              >
                                {s.title}
                              </span>
                              {s.deprecated && (
                                <span
                                  className="rounded-sm border px-1 font-mono text-micro tracking-wide text-muted-foreground uppercase"
                                  title="Excluded from retrieval"
                                >
                                  deprecated
                                </span>
                              )}
                            </div>
                            <div className="font-mono text-caption text-muted-foreground/70">
                              {s.filename}
                            </div>
                            {v?.error_message && (
                              <div className="mt-1 text-meta text-destructive">{v.error_message}</div>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className={cn(td, "numeric text-meta text-foreground/80")}>
                        {v ? `v${v.version_number}` : "—"}
                        {v && !v.is_current && (
                          <span className="ml-1.5 font-sans text-caption text-muted-foreground/70">
                            not current
                          </span>
                        )}
                      </TableCell>
                      <TableCell className={td}>
                        {v ? <StatusBadge status={v.status} /> : "—"}
                      </TableCell>
                      <TableCell className={cn(td, "numeric text-right text-meta text-muted-foreground")}>
                        {v ? formatBytes(v.file_size_bytes) : "—"}
                      </TableCell>
                      <TableCell className={cn(td, "text-small text-muted-foreground")}>
                        {timeAgo(v?.processed_at)}
                      </TableCell>
                      <TableCell className={cn(td, "py-2")}>
                        <div className="flex items-center justify-end gap-1">
                          <Button size="sm" onClick={() => setViewing(s)}>
                            Chunks
                          </Button>
                          {admin && (
                            <RowMenu
                              source={s}
                              reindexing={reindexing === s.id}
                              onReindex={() => void reindex(s)}
                              onToggleDeprecated={() => void toggleDeprecated(s)}
                            />
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </>
      )}

      <ChunkViewer source={viewing} onClose={() => setViewing(null)} />
    </div>
  );
}

/** Admin-only row actions behind a "more" button. */
function RowMenu({
  source,
  reindexing,
  onReindex,
  onToggleDeprecated,
}: {
  source: Source;
  reindexing: boolean;
  onReindex: () => void;
  onToggleDeprecated: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <ShadButton
          variant="ghost"
          size="icon"
          aria-label={`More actions for ${source.title}`}
          className="text-muted-foreground"
        >
          {reindexing ? <Spinner className="size-3.5" /> : <MoreHorizontal />}
        </ShadButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-auto min-w-44">
        <DropdownMenuLabel className="eyebrow">Source</DropdownMenuLabel>
        <DropdownMenuItem disabled={reindexing} onSelect={onReindex}>
          <Icon name="refresh" />
          {reindexing ? "Reindexing…" : "Reindex"}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant={source.deprecated ? "default" : "destructive"}
          onSelect={onToggleDeprecated}
        >
          <Icon name={source.deprecated ? "check" : "close"} />
          {source.deprecated ? "Restore" : "Deprecate"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
