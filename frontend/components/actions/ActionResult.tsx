import type { Action } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { JsonView, StatusBadge } from "../ui";

/** Outcome of a decided action: status, final value, executor result or error. */
export function ActionResult({ action }: { action: Action }) {
  return (
    <div className="space-y-2 text-[13px]" data-testid="action-result">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={action.status} />
        {action.decided_at && (
          <span className="text-[12px] text-ink-3">decided {formatDate(action.decided_at)}</span>
        )}
      </div>
      {action.final_value != null && action.final_value !== action.value && (
        <p className="text-[12px] text-ink-2">
          Approved with edited value: <span className="font-medium">{action.final_value}</span>
        </p>
      )}
      {action.decision_note && (
        <p className="text-[12px] text-ink-2">Note: {action.decision_note}</p>
      )}
      {action.error && (
        <p className="rounded-lg bg-bad-soft px-2 py-1 text-[12px] text-bad">Error: {action.error}</p>
      )}
      {action.result != null && (
        <details>
          <summary className="cursor-pointer text-[12px] text-ink-3">Executor result</summary>
          <JsonView value={action.result} className="mt-1" />
        </details>
      )}
    </div>
  );
}
