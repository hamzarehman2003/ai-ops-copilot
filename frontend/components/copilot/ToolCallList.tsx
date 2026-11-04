import type { ToolCallOut } from "@/lib/api";
import { formatMs } from "@/lib/format";
import { Icon } from "../icons";
import { JsonView, StatusBadge } from "../ui";

/** Collapsible list of tool calls made while answering (arguments + result JSON). */
export function ToolCallList({ calls }: { calls: ToolCallOut[] }) {
  if (calls.length === 0) return null;
  return (
    <details className="group/tools rounded-xl border border-line bg-paper/40">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3.5 py-2.5 text-[12.5px] text-ink-2">
        <Icon
          name="chevronRight"
          className="h-3.5 w-3.5 text-ink-3 transition-transform group-open/tools:rotate-90"
        />
        <Icon name="bolt" className="h-3.5 w-3.5 text-ink-3" />
        <span className="font-medium">
          {calls.length} tool call{calls.length === 1 ? "" : "s"}
        </span>
        <span className="ml-1 inline-flex gap-1">
          {calls.map((c) => (
            <StatusBadge key={c.id} status={c.status} />
          ))}
        </span>
      </summary>
      <ul className="space-y-2 px-3.5 pb-3.5">
        {calls.map((c) => (
          <li key={c.id} className="rounded-lg border border-line bg-surface">
            <details className="group/call">
              <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-2 text-[12px]">
                <Icon
                  name="chevronRight"
                  className="h-3 w-3 text-ink-4 transition-transform group-open/call:rotate-90"
                />
                <span className="font-mono font-medium text-ink">{c.tool_name}</span>
                <StatusBadge status={c.status} />
                {c.error_code && <span className="font-mono text-bad">{c.error_code}</span>}
                <span className="ml-auto font-mono text-[11px] text-ink-3">
                  {c.attempts} attempt{c.attempts === 1 ? "" : "s"} · {formatMs(c.latency_ms)}
                </span>
              </summary>
              <div className="grid gap-3 border-t border-line p-3 lg:grid-cols-2">
                <div>
                  <div className="eyebrow mb-1.5">Arguments</div>
                  <JsonView value={c.arguments} />
                </div>
                <div>
                  <div className="eyebrow mb-1.5">Result</div>
                  <JsonView value={c.result} />
                </div>
              </div>
            </details>
          </li>
        ))}
      </ul>
    </details>
  );
}
