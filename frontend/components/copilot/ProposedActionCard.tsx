"use client";

import { useState } from "react";
import type { Action, ProposedActionSummary } from "@/lib/api";
import { ActionDecision } from "../actions/ActionDecision";
import { ActionResult } from "../actions/ActionResult";
import { Icon } from "../icons";
import { Badge, Card } from "../ui";

export const ACTION_LABELS: Record<string, string> = {
  add_ticket_note: "Add internal note",
  add_ticket_tag: "Add tag",
  set_ticket_status: "Set ticket status",
};

/** The write action the copilot proposed. Nothing runs until a human approves it. */
export function ProposedActionCard({ proposal }: { proposal: ProposedActionSummary }) {
  const [decided, setDecided] = useState<Action | null>(null);

  return (
    <Card className="border border-primary/25" data-testid="proposed-action">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2 border-b border-primary/15 bg-primary/5 px-4 py-3">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-card text-primary">
          <Icon name="approve" className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="eyebrow text-primary/80">Proposed action</p>
          <p className="mt-0.5 flex flex-wrap items-baseline gap-x-2 text-body font-medium text-foreground">
            {ACTION_LABELS[proposal.type] ?? proposal.type}
            <span className="font-mono text-caption font-normal text-muted-foreground">
              on {proposal.ticket_id}
            </span>
          </p>
        </div>
        {!decided && proposal.id != null && (
          <Badge tone="amber" className="h-[22px] px-2 font-sans text-caption font-medium">
            Needs approval
          </Badge>
        )}
      </div>
      <div className="p-4">
        {proposal.reason && (
          <p className="mb-3.5 text-ui leading-relaxed text-foreground/80">
            <span className="text-muted-foreground">Why: </span>
            {proposal.reason}
          </p>
        )}

        {proposal.id == null ? (
          <div className="space-y-2 text-ui">
            <p className="text-foreground/80">
              Value: <span className="font-medium text-foreground">{proposal.value}</span>
            </p>
            <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-1.5 text-meta text-destructive">
              Not recorded{proposal.error ? `: ${proposal.error}` : ""}
            </p>
          </div>
        ) : decided ? (
          <ActionResult action={decided} />
        ) : (
          <ActionDecision
            actionId={proposal.id}
            actionType={proposal.type}
            value={proposal.value}
            onDecided={setDecided}
          />
        )}
      </div>
    </Card>
  );
}
