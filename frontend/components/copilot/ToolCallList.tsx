"use client";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { ToolCallOut } from "@/lib/api";
import { formatMs } from "@/lib/format";
import { Icon } from "../icons";
import { Card, JsonView, StatusBadge } from "../ui";

/** Collapsible list of tool calls made while answering (arguments + result JSON). */
export function ToolCallList({ calls }: { calls: ToolCallOut[] }) {
  if (calls.length === 0) return null;
  return (
    <Collapsible asChild>
      <Card className="group/tools border">
        <CollapsibleTrigger className="flex w-full cursor-pointer items-center gap-2 px-3.5 py-2.5 text-left text-[12.5px] text-foreground/85 transition-colors outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:ring-inset">
          <Icon
            name="chevronRight"
            className="size-3.5 text-muted-foreground transition-transform group-data-[state=open]/tools:rotate-90"
          />
          <Icon name="bolt" className="size-3.5 text-muted-foreground" />
          <span className="font-medium">
            {calls.length} tool call{calls.length === 1 ? "" : "s"}
          </span>
          <span className="ml-1 inline-flex flex-wrap gap-1">
            {calls.map((c) => (
              <StatusBadge key={c.id} status={c.status} />
            ))}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ul className="space-y-2 border-t bg-muted/40 p-3">
            {calls.map((c) => (
              <li key={c.id}>
                <ToolCall call={c} />
              </li>
            ))}
          </ul>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

function ToolCall({ call: c }: { call: ToolCallOut }) {
  return (
    <Collapsible asChild>
      <Card className="group/call border">
        <CollapsibleTrigger className="flex w-full cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-left text-[12px] transition-colors outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:ring-inset">
          <Icon
            name="chevronRight"
            className="size-3 text-muted-foreground/70 transition-transform group-data-[state=open]/call:rotate-90"
          />
          <span className="font-mono font-medium text-foreground">{c.tool_name}</span>
          <StatusBadge status={c.status} />
          {c.error_code && <span className="font-mono text-destructive">{c.error_code}</span>}
          <span className="numeric ml-auto text-[11px] text-muted-foreground">
            {c.attempts} attempt{c.attempts === 1 ? "" : "s"} · {formatMs(c.latency_ms)}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="grid gap-3 border-t p-3 lg:grid-cols-2">
            <div className="min-w-0">
              <div className="eyebrow mb-1.5">Arguments</div>
              <JsonView value={c.arguments} />
            </div>
            <div className="min-w-0">
              <div className="eyebrow mb-1.5">Result</div>
              <JsonView value={c.result} />
            </div>
          </div>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
