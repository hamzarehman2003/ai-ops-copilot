"use client";

import { useState } from "react";
import { api, type Action } from "@/lib/api";
import { canDecide } from "@/lib/roles";
import { useRole } from "../UserProvider";
import { Button, ErrorBanner, inputClass } from "../ui";

const TICKET_STATUSES = ["open", "pending", "solved"];

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
  const [edited, setEdited] = useState(value);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<unknown>(null);

  if (!canDecide(role)) {
    return (
      <p className="text-[12px] text-ink-3" data-testid="decision-not-allowed">
        Your role ({role ?? "…"}) can view this action but cannot approve or reject it.
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
      onDecided(action);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-2">
      <label className="block text-[12px] font-medium text-ink-2">
        Value {edited !== value && <span className="text-accent-ink">(edited)</span>}
        {actionType === "set_ticket_status" ? (
          <select
            className={`${inputClass} mt-1`}
            value={edited}
            onChange={(e) => setEdited(e.target.value)}
          >
            {!TICKET_STATUSES.includes(edited) && <option value={edited}>{edited}</option>}
            {TICKET_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        ) : actionType === "add_ticket_note" ? (
          <textarea
            className={`${inputClass} mt-1 min-h-20`}
            value={edited}
            maxLength={2000}
            onChange={(e) => setEdited(e.target.value)}
          />
        ) : (
          <input
            className={`${inputClass} mt-1`}
            value={edited}
            onChange={(e) => setEdited(e.target.value)}
          />
        )}
      </label>
      <input
        className={inputClass}
        placeholder="Decision note (optional)"
        value={note}
        maxLength={1000}
        onChange={(e) => setNote(e.target.value)}
      />
      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <div className="flex gap-2">
        <Button
          variant="success"
          size="sm"
          disabled={busy !== null}
          onClick={() => decide("approve")}
        >
          {busy === "approve" ? "Approving…" : edited !== value ? "Approve edited" : "Approve"}
        </Button>
        <Button variant="danger" size="sm" disabled={busy !== null} onClick={() => decide("reject")}>
          {busy === "reject" ? "Rejecting…" : "Reject"}
        </Button>
      </div>
    </div>
  );
}
