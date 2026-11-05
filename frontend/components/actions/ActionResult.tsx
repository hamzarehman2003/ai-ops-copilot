"use client";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Action } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Icon } from "../icons";
import { JsonView, StatusBadge } from "../ui";

/** Outcome of a decided action: status, final value, executor result or error. */
export function ActionResult({ action }: { action: Action }) {
  return (
    <div className="space-y-2.5 text-[13px]" data-testid="action-result">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={action.status} />
        {action.decided_at && (
          <span className="text-[12px] text-muted-foreground">
            decided {formatDate(action.decided_at)}
          </span>
        )}
      </div>
      {action.final_value != null && action.final_value !== action.value && (
        <div className="rounded-md border bg-card px-3 py-2">
          <div className="eyebrow mb-0.5">Approved with edited value</div>
          <div className="text-[12.5px] whitespace-pre-wrap text-foreground">
            {action.final_value}
          </div>
        </div>
      )}
      {action.decision_note && (
        <p className="text-[12px] text-foreground/80">
          <span className="text-muted-foreground">Note: </span>
          {action.decision_note}
        </p>
      )}
      {action.error && (
        <p className="flex items-start gap-1.5 rounded-md border border-destructive/30 bg-destructive/10 px-2.5 py-1.5 text-[12px] text-destructive">
          <Icon name="alert" className="mt-px size-3.5 shrink-0" />
          <span>Error: {action.error}</span>
        </p>
      )}
      {action.result != null && (
        <Collapsible className="group/result">
          <CollapsibleTrigger className="inline-flex cursor-pointer items-center gap-1 rounded-sm text-[12px] text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/30">
            <Icon
              name="chevronRight"
              className="size-3.5 transition-transform group-data-[state=open]/result:rotate-90"
            />
            Executor result
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-1.5">
            <JsonView value={action.result} />
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
