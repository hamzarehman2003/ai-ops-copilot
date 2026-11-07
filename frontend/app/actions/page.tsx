"use client";

import { useState } from "react";
import { ActionDecision } from "@/components/actions/ActionDecision";
import { ActionResult } from "@/components/actions/ActionResult";
import { RetryAction } from "@/components/actions/RetryAction";
import { ACTION_LABELS } from "@/components/copilot/ProposedActionCard";
import { Icon } from "@/components/icons";
import {
  Badge,
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
          <Button onClick={() => void actions.reload()} disabled={actions.loading}>
            <Icon name="refresh" className="size-3.5" />
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
        <EmptyState
          title={tab === "pending" ? "Inbox zero" : "No decisions yet"}
          icon={tab === "pending" ? "approve" : "list"}
        >
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
      <Badge className="h-[18px] rounded-full px-1.5 text-[10.5px]">{count}</Badge>
    </span>
  );
}

function ActionRow({ action, onDecided }: { action: Action; onDecided: (a: Action) => void }) {
  return (
    <Card className="animate-rise overflow-hidden border" data-testid="action-row">
      <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,23rem)]">
        <div className="flex min-w-0 flex-col">
          <div className="min-w-0 flex-1 space-y-3 p-5">
            <div className="flex flex-wrap items-start gap-x-3 gap-y-1.5">
              <div className="min-w-0">
                <p className="eyebrow">Proposed action</p>
                <h2 className="mt-0.5 text-[15px] font-semibold tracking-[-0.01em] text-foreground">
                  {ACTION_LABELS[action.action_type] ?? action.action_type}
                </h2>
              </div>
              <StatusBadge status={action.status} className="mt-1" />
              <span className="ml-auto pt-0.5 text-[12px] text-muted-foreground">
                {timeAgo(action.created_at)}
              </span>
            </div>
            <div className="text-[13px] text-foreground/80">
              <span className="font-medium text-foreground">{action.customer}</span>
              <span className="mx-1.5 text-muted-foreground/50">/</span>
              <span className="font-mono text-[12px]">{action.ticket}</span>
              <span className="mx-1.5 text-muted-foreground/50">/</span>
              {action.ticket_subject}
            </div>
            <div className="rounded-md border bg-muted/40 px-3.5 py-2.5">
              <div className="eyebrow mb-1">Proposed value</div>
              <div className="text-[13.5px] whitespace-pre-wrap text-foreground">{action.value}</div>
            </div>
            {action.reason && (
              <p className="text-[13px] leading-relaxed text-foreground/80">
                <span className="text-muted-foreground">Why: </span>
                {action.reason}
              </p>
            )}
          </div>
          <p className="border-t bg-muted/40 px-5 py-2.5 font-mono text-[10.5px] text-muted-foreground">
            proposed by {shortId(action.proposed_by)}
            {action.decided_by && ` · decided by ${shortId(action.decided_by)}`}
            {action.message_id && ` · message ${shortId(action.message_id)}`}
          </p>
        </div>
        <div className="border-t bg-muted/20 p-5 md:border-t-0 md:border-l">
          {action.status === "pending" ? (
            <ActionDecision
              actionId={action.id}
              actionType={action.action_type}
              value={action.value}
              onDecided={onDecided}
            />
          ) : (
            <>
              <ActionResult action={action} />
              <RetryAction action={action} onDone={onDecided} />
            </>
          )}
        </div>
      </div>
    </Card>
  );
}
