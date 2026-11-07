"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { Spinner } from "@/components/ui";
import type { ProgressEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

type StepState = "active" | "done" | "failed";
type Step = { key: string; label: string; detail?: string; state: StepState };

const TOOL_LABELS: Record<string, string> = {
  get_account_status: "Checking the account in the CRM",
  get_recent_tickets: "Reading the customer's recent tickets",
};

/** Fold the server's progress events into a checklist: one row per step, the newest active. */
export function toSteps(events: ProgressEvent[]): Step[] {
  const steps: Step[] = [];
  const push = (step: Step) => {
    for (const s of steps) if (s.state === "active") s.state = "done";
    steps.push(step);
  };
  for (const e of events) {
    switch (e.step) {
      case "retrieving":
        push({ key: "search", label: "Searching the knowledge base", state: "active" });
        break;
      case "rewriting":
        push({
          key: "rewrite",
          label: "Weak match, searching again in the docs' terms",
          detail: e.queries.join(" · "),
          state: "active",
        });
        break;
      case "retrieved": {
        // The latest search: the first one, or the retry after a rewrite.
        const search = [...steps].reverse().find((s) => s.key === "search" || s.key === "rewrite");
        if (search) {
          search.state = "done";
          if (search.key === "rewrite") break; // keep the queries as its detail
          search.label = "Searched the knowledge base";
          search.detail =
            e.count === 0
              ? "no relevant passages"
              : `${e.count} passage${e.count === 1 ? "" : "s"} · ${e.documents.slice(0, 3).join(", ")}`;
        }
        break;
      }
      case "model":
        push({
          key: `model-${e.round}`,
          label: e.round === 1 ? "Model is reading the sources" : "Model is drafting with tool results",
          detail: e.model,
          state: "active",
        });
        break;
      case "tool":
        push({
          key: `tool-${steps.length}`,
          label: TOOL_LABELS[e.name] ?? `Calling ${e.name}`,
          detail: e.name,
          state: "active",
        });
        break;
      case "tool_done": {
        const tool = [...steps].reverse().find((s) => s.detail === e.name && s.state === "active");
        if (tool) {
          tool.state = e.ok ? "done" : "failed";
          if (!e.ok) tool.detail = `${e.name} · ${e.error ?? "failed"}`;
        }
        break;
      }
      case "llm_failed": {
        const model = [...steps].reverse().find((s) => s.key.startsWith("model-"));
        if (model) model.state = "failed";
        push({
          key: "fallback",
          label: "Model unavailable, falling back to cited evidence",
          detail: e.error.slice(0, 120),
          state: "active",
        });
        break;
      }
      case "checking":
        push({ key: "checking", label: "Checking citations and policy", state: "active" });
        break;
    }
  }
  return steps;
}

export function ProgressSteps({ events, startedAt }: { events: ProgressEvent[]; startedAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, []);

  const steps = toSteps(events);
  return (
    <div className="min-w-0 flex-1 pt-0.5" aria-live="polite">
      <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
        <span className="eyebrow">Working</span>
        <span className="tabular-nums">{((now - startedAt) / 1000).toFixed(1)} s</span>
      </div>
      <ol className="mt-2 space-y-1.5" data-testid="progress-steps">
        {steps.length === 0 && (
          <li className="flex items-center gap-2.5 text-[13px] text-muted-foreground">
            <Spinner className="size-3.5" />
            Starting…
          </li>
        )}
        {steps.map((s) => (
          <li key={s.key} className="flex animate-rise items-start gap-2.5 text-[13px]" data-state={s.state}>
            <span className="mt-0.5 flex size-3.5 shrink-0 items-center justify-center">
              {s.state === "active" ? (
                <Spinner className="size-3.5" />
              ) : s.state === "done" ? (
                <Icon name="check" className="size-3.5 text-primary" />
              ) : (
                <Icon name="alert" className="size-3.5 text-amber-600 dark:text-amber-400" />
              )}
            </span>
            <span className="min-w-0">
              <span className={cn(s.state === "active" ? "text-foreground" : "text-foreground/75")}>
                {s.label}
              </span>
              {s.detail && (
                <span className="ml-2 font-mono text-[11.5px] break-words text-muted-foreground">
                  {s.detail}
                </span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
