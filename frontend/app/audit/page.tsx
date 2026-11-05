"use client";

import { Fragment, useMemo, useState } from "react";
import { Icon } from "@/components/icons";
import { Button, EmptyState, ErrorBanner, JsonView, Loading, PageHeader } from "@/components/ui";
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
import { api, type AuditEvent } from "@/lib/api";
import { formatDate, shortId } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { cn } from "@/lib/utils";

const FAILURE = /(fail|denied|error|reject)/;

function eventDot(type: string): string {
  if (FAILURE.test(type)) return "bg-destructive";
  if (type.startsWith("action.")) return "bg-primary";
  if (type.startsWith("source.")) return "bg-info";
  return "bg-muted-foreground/60";
}

const FILTERS = [
  { value: "all", label: "All", match: () => true },
  { value: "sources", label: "Sources", match: (e: AuditEvent) => e.event_type.startsWith("source.") },
  { value: "actions", label: "Actions", match: (e: AuditEvent) => e.event_type.startsWith("action.") },
  { value: "failures", label: "Failures", match: (e: AuditEvent) => FAILURE.test(e.event_type) },
] as const;
type Filter = (typeof FILTERS)[number]["value"];

function actorLabel(e: AuditEvent): string {
  return e.actor_name ?? (e.actor_user_id ? shortId(e.actor_user_id) : "System");
}

const th = "h-10 px-5 text-[10.5px] font-medium tracking-[0.1em] text-muted-foreground uppercase";

export default function AuditPage() {
  const events = useAsync<AuditEvent[]>(() => api.auditEvents(200), []);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const sorted = useMemo(
    () => [...(events.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [events.data],
  );

  const searched = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter((e) =>
      [e.event_type, e.entity_type, e.entity_id, actorLabel(e)].some((f) =>
        f.toLowerCase().includes(q),
      ),
    );
  }, [sorted, query]);

  const counts = Object.fromEntries(
    FILTERS.map((f) => [f.value, searched.filter(f.match).length]),
  ) as Record<Filter, number>;
  const activeMatch = FILTERS.find((f) => f.value === filter)?.match ?? (() => true);
  const visible = searched.filter(activeMatch);

  const toggle = (id: string) =>
    setOpen((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="animate-rise">
      <PageHeader
        eyebrow="Governance"
        title="Audit log"
        description="Every upload, indexing run, proposal and decision, newest first. Append-only."
        actions={
          <Button onClick={() => void events.reload()}>
            <Icon name="refresh" className="h-3.5 w-3.5" />
            Refresh
          </Button>
        }
      />
      {events.loading && !events.data ? (
        <Loading />
      ) : events.error ? (
        <ErrorBanner error={events.error} />
      ) : sorted.length === 0 ? (
        <EmptyState title="No audit events yet" />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b">
            <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
              <TabsList variant="line" className="h-10 gap-5 p-0">
                {FILTERS.map((f) => (
                  <TabsTrigger key={f.value} value={f.value} className="flex-none px-0.5 text-[13.5px]">
                    {f.label}
                    <span className="numeric text-[11px] text-muted-foreground">{counts[f.value]}</span>
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <InputGroup className="mb-2 w-full bg-card shadow-card sm:w-72">
              <InputGroupAddon>
                <Icon name="search" />
              </InputGroupAddon>
              <InputGroupInput
                type="search"
                placeholder="Filter by event, entity or actor"
                aria-label="Filter audit events"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </InputGroup>
          </div>

          <div className="overflow-hidden rounded-lg border bg-card shadow-card">
            <Table className="text-[13px]" data-testid="audit-table">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className={th}>When</TableHead>
                  <TableHead className={th}>Event</TableHead>
                  <TableHead className={th}>Entity</TableHead>
                  <TableHead className={th}>Actor</TableHead>
                  <TableHead className={th}>Data</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.length === 0 ? (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={5} className="px-5 py-10 text-center text-muted-foreground">
                      No events match this filter.
                    </TableCell>
                  </TableRow>
                ) : (
                  visible.map((e) => {
                    const isOpen = open.has(e.id);
                    return (
                      <Fragment key={e.id}>
                        <TableRow className={cn(isOpen && "border-b-0")}>
                          <TableCell className="numeric px-5 py-3 text-[11.5px] text-muted-foreground">
                            {formatDate(e.created_at)}
                          </TableCell>
                          <TableCell className="px-5 py-3">
                            <span className="inline-flex items-center gap-2 font-mono text-[12px] text-foreground">
                              <span
                                className={cn("size-1.5 shrink-0 rounded-full", eventDot(e.event_type))}
                                aria-hidden
                              />
                              {e.event_type}
                            </span>
                          </TableCell>
                          <TableCell className="px-5 py-3 text-[12.5px]">
                            <span className="text-foreground/80">{e.entity_type}</span>{" "}
                            <span
                              className="font-mono text-[11px] text-muted-foreground"
                              title={e.entity_id}
                            >
                              {shortId(e.entity_id)}
                            </span>
                          </TableCell>
                          <TableCell className="px-5 py-3 text-[12.5px] text-foreground/80">
                            {actorLabel(e)}
                          </TableCell>
                          <TableCell className="max-w-md px-5 py-3">
                            <button
                              type="button"
                              onClick={() => toggle(e.id)}
                              aria-expanded={isOpen}
                              className="flex w-full items-center gap-1.5 truncate rounded-sm text-left font-mono text-[11.5px] text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
                              title={isOpen ? "Hide JSON" : "Show JSON"}
                            >
                              <Icon
                                name="chevronRight"
                                className={cn(
                                  "size-3 shrink-0 transition-transform",
                                  isOpen && "rotate-90",
                                )}
                              />
                              <span className="truncate">{isOpen ? "hide" : summarize(e.data)}</span>
                            </button>
                          </TableCell>
                        </TableRow>
                        {isOpen && (
                          <TableRow className="bg-muted/50 hover:bg-muted/50">
                            <TableCell colSpan={5} className="px-5 pt-0 pb-4 whitespace-normal">
                              <JsonView value={e.data} />
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  );
}

function summarize(data: Record<string, unknown>): string {
  const s = Object.entries(data)
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" ");
  return s || "{}";
}
