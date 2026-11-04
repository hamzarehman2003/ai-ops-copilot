"use client";

import { Fragment, useState } from "react";
import { Icon } from "@/components/icons";
import {
  Button,
  Card,
  cx,
  EmptyState,
  ErrorBanner,
  JsonView,
  Loading,
  PageHeader,
} from "@/components/ui";
import { api, type AuditEvent } from "@/lib/api";
import { formatDate, shortId } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";

function eventDot(type: string): string {
  if (/(fail|denied|error|reject)/.test(type)) return "bg-bad";
  if (type.startsWith("action.")) return "bg-accent";
  if (type.startsWith("source.")) return "bg-info";
  return "bg-ink-4";
}

const th = "eyebrow px-5 py-3 font-medium";

export default function AuditPage() {
  const events = useAsync<AuditEvent[]>(() => api.auditEvents(200), []);
  const [open, setOpen] = useState<Set<string>>(new Set());

  const sorted = [...(events.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));
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
        <Card className="overflow-x-auto">
          <table className="w-full text-left text-[13px]" data-testid="audit-table">
            <thead className="border-b border-line">
              <tr>
                <th className={th}>When</th>
                <th className={th}>Event</th>
                <th className={th}>Entity</th>
                <th className={th}>Actor</th>
                <th className={th}>Data</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {sorted.map((e) => (
                <Fragment key={e.id}>
                  <tr className="align-middle transition-colors hover:bg-paper/60">
                    <td className="px-5 py-3 font-mono text-[11.5px] whitespace-nowrap text-ink-3">
                      {formatDate(e.created_at)}
                    </td>
                    <td className="px-5 py-3">
                      <span className="inline-flex items-center gap-2 font-mono text-[12px] text-ink">
                        <span className={cx("h-1.5 w-1.5 rounded-full", eventDot(e.event_type))} />
                        {e.event_type}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-[12.5px] whitespace-nowrap">
                      <span className="text-ink-2">{e.entity_type}</span>{" "}
                      <span className="font-mono text-[11px] text-ink-4" title={e.entity_id}>
                        {shortId(e.entity_id)}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-[12.5px] whitespace-nowrap text-ink-2">
                      {e.actor_name ?? (e.actor_user_id ? shortId(e.actor_user_id) : "System")}
                    </td>
                    <td className="max-w-md px-5 py-3">
                      <button
                        type="button"
                        onClick={() => toggle(e.id)}
                        className="flex w-full items-center gap-1.5 truncate text-left font-mono text-[11.5px] text-ink-3 hover:text-ink"
                        title="Show JSON"
                      >
                        <Icon
                          name="chevronRight"
                          className={cx(
                            "h-3 w-3 shrink-0 transition-transform",
                            open.has(e.id) && "rotate-90",
                          )}
                        />
                        <span className="truncate">{open.has(e.id) ? "hide" : summarize(e.data)}</span>
                      </button>
                    </td>
                  </tr>
                  {open.has(e.id) && (
                    <tr>
                      <td colSpan={5} className="bg-paper/60 px-5 py-3">
                        <JsonView value={e.data} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </Card>
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
