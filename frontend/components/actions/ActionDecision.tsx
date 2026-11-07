"use client";

import { useId, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage, type Action } from "@/lib/api";
import { canDecide } from "@/lib/roles";
import { Icon } from "../icons";
import { useRole } from "../UserProvider";
import { Badge, Button, ErrorBanner } from "../ui";

const TICKET_STATUSES = ["open", "pending", "solved"];

const field = "bg-card shadow-card";

/** Value editor + Approve / Reject for one pending action. Hidden for roles that can't decide. */
export function ActionDecision({
  actionId,
  actionType,
  value,
  onDecided,
}: {
  actionId: string;
  actionType: string;
  value: string;
  onDecided: (action: Action) => void;
}) {
  const role = useRole();
  const ids = useId();
  const [edited, setEdited] = useState(value);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<unknown>(null);

  if (!canDecide(role)) {
    return (
      <p
        className="flex items-start gap-2 rounded-md border border-dashed px-3 py-2.5 text-meta leading-relaxed text-muted-foreground"
        data-testid="decision-not-allowed"
      >
        <Icon name="shield" className="mt-px size-3.5 shrink-0" />
        <span>
          Your role ({role ?? "…"}) can view this action but cannot approve or reject it.
        </span>
      </p>
    );
  }

  const decide = async (kind: "approve" | "reject") => {
    setBusy(kind);
    setError(null);
    try {
      const noteValue = note.trim() || null;
      const action =
        kind === "approve"
          ? await api.approve(actionId, {
              edited_value: edited !== value ? edited : null,
              note: noteValue,
            })
          : await api.reject(actionId, { note: noteValue });
      if (kind === "reject") {
        toast("Action rejected", { description: "Nothing was changed on the ticket." });
      } else if (action.status === "failed" || action.error) {
        toast.error("Approved, but execution failed", {
          description: action.error ?? undefined,
        });
      } else if (action.status === "executed") {
        toast.success("Action approved and executed");
      } else {
        // Only claim execution when the executor confirmed it.
        toast("Action approved", { description: `Status: ${action.status}` });
      }
      onDecided(action);
    } catch (e) {
      setError(e);
      toast.error(kind === "approve" ? "Couldn't approve the action" : "Couldn't reject the action", {
        description: errorMessage(e),
      });
    } finally {
      setBusy(null);
    }
  };

  const valueId = `${ids}-value`;
  const noteId = `${ids}-note`;

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor={valueId} className="eyebrow text-caption leading-normal">
          Value
          {edited !== value && (
            <Badge tone="indigo" className="h-4 px-1 font-sans text-micro tracking-normal normal-case">
              edited
            </Badge>
          )}
        </Label>
        {actionType === "set_ticket_status" ? (
          <NativeSelect
            id={valueId}
            className={`w-full ${field} rounded-lg`}
            value={edited}
            onChange={(e) => setEdited(e.target.value)}
          >
            {!TICKET_STATUSES.includes(edited) && (
              <NativeSelectOption value={edited}>{edited}</NativeSelectOption>
            )}
            {TICKET_STATUSES.map((s) => (
              <NativeSelectOption key={s} value={s}>
                {s}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        ) : actionType === "add_ticket_note" ? (
          <Textarea
            id={valueId}
            className={`${field} min-h-20`}
            value={edited}
            maxLength={2000}
            onChange={(e) => setEdited(e.target.value)}
          />
        ) : (
          <Input
            id={valueId}
            className={field}
            value={edited}
            onChange={(e) => setEdited(e.target.value)}
          />
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={noteId} className="eyebrow text-caption leading-normal">
          Decision note
        </Label>
        <Input
          id={noteId}
          className={field}
          placeholder="Optional, saved to the audit log"
          value={note}
          maxLength={1000}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <div className="flex gap-2 pt-0.5">
        <Button
          variant="success"
          size="sm"
          disabled={busy !== null}
          onClick={() => decide("approve")}
        >
          <Icon name="check" className="size-3.5" />
          {busy === "approve" ? "Approving…" : edited !== value ? "Approve edited" : "Approve"}
        </Button>
        <Button variant="danger" size="sm" disabled={busy !== null} onClick={() => decide("reject")}>
          <Icon name="close" className="size-3.5" />
          {busy === "reject" ? "Rejecting…" : "Reject"}
        </Button>
      </div>
    </div>
  );
}
