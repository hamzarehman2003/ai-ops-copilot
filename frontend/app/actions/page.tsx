"use client";

import { useState } from "react";
import { ActionDecision } from "@/components/actions/ActionDecision";
import { ActionResult } from "@/components/actions/ActionResult";
import { ACTION_LABELS } from "@/components/copilot/ProposedActionCard";
import { Icon } from "@/components/icons";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Loading,
  PageHeader,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import { api, type Action } from "@/lib/api";
import { shortId, timeAgo } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";

type Tab = "pending" | "history";

export default function ActionsPage() {
  const [tab, setTab] = useState<Tab>("pending");
  const actions = useAsync<Action[]>(() => api.actions(), []);

  const all = actions.data ?? [];
  const pending = all.filter((a) => a.status === "pending");
  const history = all.filter((a) => a.status !== "pending");
  const shown = tab === "pending" ? pending : history;

  const replace = (updated: Action) =>
    actions.setData((list) => list?.map((a) => (a.id === updated.id ? updated : a)));

  return (
    <div className="animate-rise">
      <PageHeader
        eyebrow="Governance"
        title="Approvals"
        description="Ticket changes the copilot proposed. Nothing touches a ticket until a person approves it, and every decision lands in the audit log."
        actions={
          <Button onClick={() => void actions.reload()}>
            <Icon name="refresh" className="h-3.5 w-3.5" />
            Refresh
          </Button>
        }
      />
      <Tabs
        value={tab}
        onChange={setTab}
        options={[
          { value: "pending", label: <TabLabel label="Pending" count={pending.length} /> },
          { value: "history", label: <TabLabel label="History" count={history.length} /> },
        ]}
      />
      {actions.loading && !actions.data ? (
        <Loading />
      ) : actions.error ? (
        <ErrorBanner error={actions.error} />
      ) : shown.length === 0 ? (
        <EmptyState title={tab === "pending" ? "Inbox zero" : "No decisions yet"}>
          {tab === "pending"
            ? "Proposals appear here when the copilot (in LLM mode) suggests a ticket note, tag or status change."
            : "Approved and rejected actions will be listed here."}
        </EmptyState>
      ) : (
        <div className="space-y-3">
          {shown.map((a) => (
            <ActionRow key={a.id} action={a} onDecided={replace} />
          ))}
        </div>
      )}
    </div>
  );
}

function TabLabel({ label, count }: { label: string; count: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      {label}
      <span className="rounded-full bg-paper-2 px-1.5 font-mono text-[10.5px] leading-[18px] text-ink-3 tabular-nums">
        {count}
      </span>
    </span>
  );
}

function ActionRow({ action, onDecided }: { action: Action; onDecided: (a: Action) => void }) {
  return (
    <Card className="animate-rise overflow-hidden" data-testid="action-row">
      <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,23rem)]">
        <div className="min-w-0 space-y-3 p-5">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-[14px] font-semibold text-ink">
              {ACTION_LABELS[action.action_type] ?? action.action_type}
            </span>
            <StatusBadge status={action.status} />
            <span className="ml-auto text-[12px] text-ink-3">{timeAgo(action.created_at)}</span>
          </div>
          <div className="text-[13px] text-ink-2">
            <span className="font-medium text-ink">{action.customer}</span>
            <span className="mx-1.5 text-ink-4">/</span>
            <span className="font-mono text-[12px]">{action.ticket}</span>
            <span className="mx-1.5 text-ink-4">/</span>
            {action.ticket_subject}
          </div>
          <div className="rounded-lg border border-line bg-paper/60 px-3.5 py-2.5">
            <div className="eyebrow mb-1">Proposed value</div>
            <div className="text-[13.5px] whitespace-pre-wrap text-ink">{action.value}</div>
          </div>
          {action.reason && (
            <p className="text-[13px] leading-relaxed text-ink-2">
              <span className="text-ink-3">Why: </span>
              {action.reason}
            </p>
          )}
          <p className="font-mono text-[10.5px] text-ink-4">
            proposed by {shortId(action.proposed_by)}
            {action.decided_by && ` · decided by ${shortId(action.decided_by)}`}
            {action.message_id && ` · message ${shortId(action.message_id)}`}
          </p>
        </div>
        <div className="border-t border-line bg-paper/40 p-5 md:border-t-0 md:border-l">
          {action.status === "pending" ? (
            <ActionDecision
              actionId={action.id}
              actionType={action.action_type}
              value={action.value}
              onDecided={onDecided}
            />
          ) : (
            <ActionResult action={action} />
          )}
        </div>
      </div>
    </Card>
  );
}
