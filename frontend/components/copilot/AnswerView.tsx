"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button as ShadButton } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, errorMessage, type Citation, type QueryResponse } from "@/lib/api";
import { formatMs } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Icon } from "../icons";
import { Badge, Button } from "../ui";
import { CitationCard, citationDomId } from "./CitationCard";
import { ProposedActionCard } from "./ProposedActionCard";
import { ToolCallList } from "./ToolCallList";
import { TraceDrawer } from "./TraceDrawer";

const MARKER = /\[([ST]\d+)\]/g;

const TOOL_TITLES: Record<string, string> = {
  get_account_status: "Account status from the CRM",
  get_recent_tickets: "Recent tickets from the CRM",
};

/** One assistant answer: text with [S#] (document) and [T#] (tool result) chips, citations,
 *  tools, proposed action, feedback. */
export function AnswerView({ response }: { response: QueryResponse }) {
  const [highlight, setHighlight] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [showOthers, setShowOthers] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const citedIds = new Set(response.citations.map((c) => c.source_id));
  const others = response.sources.filter((s) => !citedIds.has(s.source_id));
  const known = new Map<string, Citation>(response.sources.map((s) => [s.source_id, s]));
  const tools = new Map(
    response.tool_calls.flatMap((c) => (c.source_id ? [[c.source_id, c.tool_name] as const] : [])),
  );

  useEffect(() => () => void (flashTimer.current && clearTimeout(flashTimer.current)), []);

  const focusSource = (sid: string) => {
    if (!citedIds.has(sid)) setShowOthers(true);
    setHighlight(sid);
    setFlash(null);
    // next frame so the "others" list is rendered and the animation restarts
    requestAnimationFrame(() => {
      setFlash(sid);
      document
        .getElementById(citationDomId(response.message_id, sid))
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(null), 1700);
  };

  return (
    <div className="space-y-4" data-testid="assistant-answer">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-[11px] text-muted-foreground">
        {response.mode === "llm" && (
          <Badge tone="indigo" className="h-[18px] px-1.5 text-[10px] tracking-[0.08em] uppercase">
            LLM
          </Badge>
        )}
        {response.model && <span>{response.model}</span>}
        <span title="Retrieval mode">{response.retrieval.mode}</span>
        <span className="text-muted-foreground/50">·</span>
        <span className="numeric" title="Total latency (retrieval latency)">
          {formatMs(response.latency_ms)}{" "}
          <span className="text-muted-foreground/60">
            (retrieval {formatMs(response.retrieval.latency_ms)})
          </span>
        </span>
      </div>

      {response.abstained && (
        <Alert
          className="border-warning/30 bg-warning/10 px-4 py-3 text-warning"
          data-testid="abstained-banner"
        >
          <Icon name="info" />
          <AlertTitle>The copilot abstained.</AlertTitle>
          <AlertDescription className="text-[13px] text-warning/90">
            The sources don&apos;t support a confident answer.
            {response.missing_information && (
              <div className="mt-1">Missing information: {response.missing_information}</div>
            )}
          </AlertDescription>
        </Alert>
      )}

      {response.warnings.map((w, i) => (
        <Alert key={i} className="border-warning/30 bg-warning/10 px-3 py-2 text-warning">
          <Icon name="alert" className="size-3.5" />
          <AlertDescription className="text-[12.5px] text-warning">{w}</AlertDescription>
        </Alert>
      ))}

      <div className="text-[14.5px] leading-[1.7] whitespace-pre-wrap text-foreground">
        {renderAnswer(response.answer, known, tools, highlight, focusSource)}
      </div>

      {response.citations.length > 0 && (
        <div className="space-y-2.5">
          <div className="eyebrow">
            Sources cited · <span className="numeric">{response.citations.length}</span>
          </div>
          <div className="grid gap-2.5 xl:grid-cols-2">
            {response.citations.map((c) => (
              <CitationCard
                key={c.source_id}
                messageId={response.message_id}
                citation={c}
                highlighted={highlight === c.source_id}
                flash={flash === c.source_id}
              />
            ))}
          </div>
        </div>
      )}

      {others.length > 0 && (
        <Collapsible open={showOthers} onOpenChange={setShowOthers}>
          <CollapsibleTrigger asChild>
            <ShadButton
              variant="ghost"
              size="sm"
              className="group/others -ml-2 font-normal text-muted-foreground"
            >
              <Icon
                name="chevronRight"
                className="size-3.5 transition-transform group-data-[state=open]/others:rotate-90"
              />
              {others.length} more retrieved source{others.length === 1 ? "" : "s"} given to the
              model
            </ShadButton>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2.5 grid gap-2.5 xl:grid-cols-2">
            {others.map((c) => (
              <CitationCard
                key={c.source_id}
                messageId={response.message_id}
                citation={c}
                highlighted={highlight === c.source_id}
                flash={flash === c.source_id}
              />
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}

      <ToolCallList calls={response.tool_calls} />

      {response.proposed_action && <ProposedActionCard proposal={response.proposed_action} />}

      <Separator />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Feedback messageId={response.message_id} />
        <Button size="sm" variant="ghost" onClick={() => setTraceOpen(true)}>
          View retrieval trace
          <Icon name="arrowUpRight" className="size-3.5" />
        </Button>
      </div>
      <TraceDrawer
        messageId={response.message_id}
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
      />
    </div>
  );
}

function renderAnswer(
  text: string,
  known: Map<string, Citation>,
  tools: Map<string, string>,
  highlight: string | null,
  onClick: (sid: string) => void,
) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(MARKER)) {
    const sid = m[1];
    const idx = m.index ?? 0;
    parts.push(<Fragment key={`t${idx}`}>{text.slice(last, idx)}</Fragment>);
    const source = known.get(sid);
    const tool = tools.get(sid);
    parts.push(
      tool ? (
        <Tooltip key={`c${idx}`}>
          <TooltipTrigger asChild>
            <span
              tabIndex={0}
              data-testid="tool-citation-chip"
              className="mx-0.5 inline-flex h-[18px] -translate-y-px items-center rounded-sm border border-primary/25 bg-primary/10 px-1.5 align-middle font-mono text-[10.5px] font-medium text-primary outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
            >
              {sid}
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" className="flex-col items-start gap-0.5">
            <span className="font-medium">{TOOL_TITLES[tool] ?? "Tool result"}</span>
            <span className="font-mono opacity-75">{tool}</span>
          </TooltipContent>
        </Tooltip>
      ) : source ? (
        <Tooltip key={`c${idx}`}>
          <TooltipTrigger asChild>
            <button
              type="button"
              data-testid="citation-chip"
              onClick={() => onClick(sid)}
              className={cn(
                "mx-0.5 inline-flex h-[18px] -translate-y-px items-center rounded-sm border px-1.5 align-middle font-mono text-[10.5px] font-medium whitespace-normal transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                highlight === sid
                  ? "border-primary bg-primary text-primary-foreground"
                  : "bg-muted text-foreground/80 hover:border-primary/30 hover:bg-primary/10 hover:text-primary",
              )}
            >
              {sid}
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="flex-col items-start gap-0.5">
            <span className="font-medium">{source.document_title}</span>
            {source.heading && <span className="opacity-75">{source.heading}</span>}
          </TooltipContent>
        </Tooltip>
      ) : (
        // A marker that doesn't match any retrieved source: show it, flagged.
        <span
          key={`c${idx}`}
          className="mx-0.5 rounded-sm border border-destructive/30 bg-destructive/10 px-1.5 font-mono text-[10.5px] text-destructive"
          title="Unknown source marker"
        >
          {sid}?
        </span>
      ),
    );
    last = idx + m[0].length;
  }
  parts.push(<Fragment key="end">{text.slice(last)}</Fragment>);
  return parts;
}

function Feedback({ messageId }: { messageId: string }) {
  const [sent, setSent] = useState<"helpful" | "unhelpful" | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async (value: "helpful" | "unhelpful") => {
    setBusy(true);
    try {
      await api.feedback(messageId, value);
      setSent(value);
      toast.success("Feedback sent", {
        description: value === "helpful" ? "Marked as helpful." : "Marked as not helpful.",
      });
    } catch (e) {
      toast.error("Couldn't send feedback", { description: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-1 text-[12px] text-muted-foreground">
      <span className="mr-1">{sent ? "Thanks, recorded." : "Was this helpful?"}</span>
      {(["helpful", "unhelpful"] as const).map((v) => (
        <ShadButton
          key={v}
          variant="ghost"
          size="icon-sm"
          disabled={busy}
          onClick={() => send(v)}
          aria-pressed={sent === v}
          aria-label={v === "helpful" ? "Helpful" : "Not helpful"}
          className={cn(
            "rounded-md text-muted-foreground",
            sent === v &&
              (v === "helpful"
                ? "border-success/30 bg-success/10 text-success hover:bg-success/15 hover:text-success"
                : "border-destructive/30 bg-destructive/10 text-destructive hover:bg-destructive/15 hover:text-destructive"),
          )}
        >
          <Icon name={v === "helpful" ? "thumbUp" : "thumbDown"} className="size-3.5" />
        </ShadButton>
      ))}
    </div>
  );
}
