"use client";

import { useState } from "react";
import { toast } from "sonner";
import { api, type Action } from "@/lib/api";
import { canDecide } from "@/lib/roles";
import { Icon } from "../icons";
import { Button, ErrorBanner } from "../ui";
import { useRole } from "../UserProvider";

/** Re-run a failed (or stuck approved) action. The server reuses the original approval and
 *  idempotency key, so a write that already landed is not applied twice. */
export function RetryAction({
  action,
  onDone,
}: {
  action: Action;
  onDone: (action: Action) => void;
}) {
  const role = useRole();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!canDecide(role) || (action.status !== "failed" && action.status !== "approved")) {
    return null;
  }

  const retry = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.retry(action.id);
      onDone(updated);
      if (updated.status === "executed") toast.success("Action executed");
      else toast.error("Still failing", { description: updated.error ?? undefined });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 space-y-2">
      <Button size="sm" onClick={() => void retry()} disabled={busy} data-testid="retry-action">
        <Icon name="refresh" className="size-3.5" />
        {busy ? "Retrying…" : "Retry"}
      </Button>
      <p className="text-caption leading-relaxed text-muted-foreground">
        Uses the original approval. Safe to repeat: the change is applied at most once.
      </p>
      {error != null && <ErrorBanner error={error} />}
    </div>
  );
}
