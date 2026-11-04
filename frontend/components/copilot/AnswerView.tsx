"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { api, type QueryResponse } from "@/lib/api";
import { formatMs } from "@/lib/format";
import { Icon } from "../icons";
import { Button, cx, ErrorBanner } from "../ui";
import { CitationCard, citationDomId } from "./CitationCard";
import { ProposedActionCard } from "./ProposedActionCard";
import { ToolCallList } from "./ToolCallList";
import { TraceDrawer } from "./TraceDrawer";

const MARKER = /\[(S\d+)\]/g;

/** One assistant answer: text with [S#] chips, citations, tools, proposed action, feedback. */
export function AnswerView({ response }: { response: QueryResponse }) {
  const [highlight, setHighlight] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [showOthers, setShowOthers] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const citedIds = new Set(response.citations.map((c) => c.source_id));
  const others = response.sources.filter((s) => !citedIds.has(s.source_id));
  const known = new Set(response.sources.map((s) => s.source_id));

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
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-[11px] text-ink-3">
        <span
          className={cx(
            "rounded px-1.5 py-0.5 tracking-wide uppercase",
            response.mode === "llm" ? "bg-accent-soft text-accent-ink" : "bg-warn-soft text-warn",
          )}
        >
          {response.mode === "llm" ? "LLM" : "offline"}
        </span>
        {response.model && <span>{response.model}</span>}
        <span title="Retrieval mode">{response.retrieval.mode}</span>
        <span className="text-ink-4">·</span>
        <span title="Total latency (retrieval latency)">
          {formatMs(response.latency_ms)}{" "}
          <span className="text-ink-4">(retrieval {formatMs(response.retrieval.latency_ms)})</span>
        </span>
      </div>

      {response.abstained && (
        <div
          className="flex gap-3 rounded-xl border border-warn/20 bg-warn-soft px-4 py-3 text-[13.5px] text-warn"
          data-testid="abstained-banner"
        >
          <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <span className="font-semibold">The copilot abstained.</span> The sources don&apos;t
            support a confident answer.
            {response.missing_information && (
              <div className="mt-1 text-warn/85">
                Missing information: {response.missing_information}
              </div>
            )}
          </div>
        </div>
      )}

      {response.warnings.map((w, i) => (
        <div
          key={i}
          className="flex gap-2 rounded-lg border border-warn/20 bg-warn-soft px-3 py-2 text-[12.5px] text-warn"
        >
          <Icon name="alert" className="mt-px h-3.5 w-3.5 shrink-0" />
          {w}
        </div>
      ))}

      <div className="text-[14.5px] leading-[1.7] whitespace-pre-wrap text-ink">
        {renderAnswer(response.answer, known, highlight, focusSource)}
      </div>

      {response.citations.length > 0 && (
        <div className="space-y-2.5">
          <div className="eyebrow">Sources cited · {response.citations.length}</div>
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
        <div>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink"
            onClick={() => setShowOthers((s) => !s)}
          >
            <Icon
              name="chevronRight"
              className={cx("h-3.5 w-3.5 transition-transform", showOthers && "rotate-90")}
            />
            {others.length} more retrieved source{others.length === 1 ? "" : "s"} given to the
            model
          </button>
          {showOthers && (
            <div className="mt-2.5 grid gap-2.5 xl:grid-cols-2">
              {others.map((c) => (
                <CitationCard
                  key={c.source_id}
                  messageId={response.message_id}
                  citation={c}
                  highlighted={highlight === c.source_id}
                  flash={flash === c.source_id}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <ToolCallList calls={response.tool_calls} />

      {response.proposed_action && <ProposedActionCard proposal={response.proposed_action} />}

      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <Feedback messageId={response.message_id} />
        <Button size="sm" variant="ghost" onClick={() => setTraceOpen(true)}>
          View retrieval trace
          <Icon name="arrowUpRight" className="h-3.5 w-3.5" />
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
  known: Set<string>,
  highlight: string | null,
  onClick: (sid: string) => void,
) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(MARKER)) {
    const sid = m[1];
    const idx = m.index ?? 0;
    parts.push(<Fragment key={`t${idx}`}>{text.slice(last, idx)}</Fragment>);
    parts.push(
      known.has(sid) ? (
        <button
          key={`c${idx}`}
          type="button"
          data-testid="citation-chip"
          onClick={() => onClick(sid)}
          className={cx(
            "mx-0.5 inline-flex h-[18px] -translate-y-px items-center rounded-[5px] px-1.5 align-middle font-mono text-[10.5px] font-medium transition-colors",
            highlight === sid
              ? "bg-accent text-white"
              : "bg-paper-2 text-ink-2 ring-1 ring-line hover:bg-accent-soft hover:text-accent-ink hover:ring-accent/30",
          )}
          title={`Show source ${sid}`}
        >
          {sid}
        </button>
      ) : (
        // A marker that doesn't match any retrieved source: show it, flagged.
        <span
          key={`c${idx}`}
          className="mx-0.5 rounded-[5px] bg-bad-soft px-1.5 font-mono text-[10.5px] text-bad"
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
  const [error, setError] = useState<unknown>(null);

  const send = async (value: "helpful" | "unhelpful") => {
    setBusy(true);
    setError(null);
    try {
      await api.feedback(messageId, value);
      setSent(value);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-1 text-[12px] text-ink-3">
      <span className="mr-1">{sent ? "Thanks, recorded." : "Was this helpful?"}</span>
      {(["helpful", "unhelpful"] as const).map((v) => (
        <button
          key={v}
          type="button"
          disabled={busy}
          onClick={() => send(v)}
          aria-pressed={sent === v}
          aria-label={v === "helpful" ? "Helpful" : "Not helpful"}
          className={cx(
            "flex h-7 w-7 items-center justify-center rounded-md border transition-colors",
            sent === v
              ? v === "helpful"
                ? "border-ok/30 bg-ok-soft text-ok"
                : "border-bad/30 bg-bad-soft text-bad"
              : "border-transparent text-ink-3 hover:border-line hover:bg-paper hover:text-ink",
          )}
        >
          <Icon name={v === "helpful" ? "thumbUp" : "thumbDown"} className="h-3.5 w-3.5" />
        </button>
      ))}
      {error != null && <ErrorBanner error={error} />}
    </div>
  );
}
