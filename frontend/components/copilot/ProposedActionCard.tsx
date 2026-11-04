"use client";

import { useState } from "react";
import type { Action, ProposedActionSummary } from "@/lib/api";
import { ActionDecision } from "../actions/ActionDecision";
import { ActionResult } from "../actions/ActionResult";
import { Icon } from "../icons";

export const ACTION_LABELS: Record<string, string> = {
  add_ticket_note: "Add internal note",
  add_ticket_tag: "Add tag",
  set_ticket_status: "Set ticket status",
};

/** The write action the copilot proposed. Nothing runs until a human approves it. */
export function ProposedActionCard({ proposal }: { proposal: ProposedActionSummary }) {
  const [decided, setDecided] = useState<Action | null>(null);

  return (
    <div
      className="overflow-hidden rounded-xl border border-accent/25 bg-surface"
      data-testid="proposed-action"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-accent/15 bg-accent-soft/60 px-4 py-2.5">
        <Icon name="approve" className="h-4 w-4 text-accent" />
        <span className="text-[13px] font-medium text-ink">
          {ACTION_LABELS[proposal.type] ?? proposal.type}
        </span>
        <span className="font-mono text-[11px] text-ink-3">on {proposal.ticket_id}</span>
        <span className="ml-auto text-[11.5px] text-accent-ink">Needs your approval</span>
      </div>
      <div className="p-4">
        {proposal.reason && (
          <p className="mb-3 text-[13px] leading-relaxed text-ink-2">{proposal.reason}</p>
        )}

        {proposal.id == null ? (
          <div className="space-y-2 text-[13px]">
            <p className="text-ink-2">
              Value: <span className="font-medium text-ink">{proposal.value}</span>
            </p>
            <p className="rounded-lg bg-bad-soft px-3 py-1.5 text-[12px] text-bad">
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
    </div>
  );
}
