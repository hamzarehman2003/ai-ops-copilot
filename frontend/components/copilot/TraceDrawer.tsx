"use client";

import { api, type MessageTrace } from "@/lib/api";
import { formatMs, formatScore } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { cx, Drawer, ErrorBanner, JsonView, Loading } from "../ui";
import { ToolCallList } from "./ToolCallList";

/** Retrieval trace for one answer: every candidate with its dense/lexical/RRF/rerank scores. */
export function TraceDrawer({
  messageId,
  open,
  onClose,
}: {
  messageId: string;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Drawer open={open} onClose={onClose} title="Retrieval trace" wide>
      {open && <TraceBody messageId={messageId} />}
    </Drawer>
  );
}

const th = "px-3 py-2.5 font-medium";
const td = "px-3 py-2";

function TraceBody({ messageId }: { messageId: string }) {
  const { data, error, loading } = useAsync<MessageTrace>(() => api.trace(messageId), [messageId]);
  if (loading) return <Loading />;
  if (error) return <ErrorBanner error={error} />;
  if (!data) return null;
  const r = data.retrieval;

  return (
    <div className="space-y-6">
      {!r ? (
        <p className="text-[13px] text-ink-3">No retrieval trace was recorded for this message.</p>
      ) : (
        <>
          <div>
            <div className="eyebrow">Query</div>
            <p className="mt-1.5 font-display text-[1.4rem] leading-snug text-ink">
              &ldquo;{r.query}&rdquo;
            </p>
            <div className="mt-3 flex flex-wrap gap-6 text-[12.5px]">
              <Fact label="Candidates" value={r.results.length} />
              <Fact label="Selected" value={r.results.filter((c) => c.selected).length} />
              <Fact label="Latency" value={formatMs(r.latency_ms)} />
            </div>
          </div>
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full text-left text-[12px]" data-testid="trace-table">
              <thead className="border-b border-line text-ink-3">
                <tr className="eyebrow">
                  <th className={th}>#</th>
                  <th className={th}>File</th>
                  <th className={th}>Heading</th>
                  <th className={cx(th, "text-right")}>Dense</th>
                  <th className={cx(th, "text-right")}>Lexical</th>
                  <th className={cx(th, "text-right")}>RRF</th>
                  <th className={cx(th, "text-right")}>Rerank</th>
                  <th className={th}>Selected</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {r.results.map((c, i) => (
                  <tr key={c.chunk_id} className={cx(c.selected ? "bg-ok-soft/50" : "text-ink-3")}>
                    <td className={cx(td, "font-mono text-ink-4 tabular-nums")}>{i + 1}</td>
                    <td className={cx(td, "font-mono whitespace-nowrap text-ink-2")}>
                      {c.filename}
                    </td>
                    <td className={cx(td, "max-w-xs truncate text-ink-2")} title={c.heading}>
                      {c.heading}
                    </td>
                    <td className={cx(td, "text-right font-mono tabular-nums")}>
                      {c.dense_rank ?? "—"}
                    </td>
                    <td className={cx(td, "text-right font-mono tabular-nums")}>
                      {c.lexical_rank ?? "—"}
                    </td>
                    <td className={cx(td, "text-right font-mono tabular-nums")}>
                      {formatScore(c.rrf_score, 4)}
                    </td>
                    <td className={cx(td, "text-right font-mono font-medium text-ink tabular-nums")}>
                      {formatScore(c.rerank_score)}
                    </td>
                    <td className={td}>
                      {c.selected ? (
                        <span className="inline-flex items-center gap-1 font-medium text-ok">
                          <span className="h-1.5 w-1.5 rounded-full bg-ok" />
                          selected
                        </span>
                      ) : (
                        ""
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary className="cursor-pointer text-[12.5px] font-medium text-ink-2">
              Retrieval params
            </summary>
            <JsonView value={r.params} className="mt-2" />
          </details>
        </>
      )}
      {data.tool_calls.length > 0 && <ToolCallList calls={data.tool_calls} />}
      <details>
        <summary className="cursor-pointer text-[12.5px] font-medium text-ink-2">
          Stored message data
        </summary>
        <JsonView value={data.message.data} className="mt-2" />
      </details>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-ink-3">{label}</div>
      <div className="font-mono text-[13px] text-ink tabular-nums">{value}</div>
    </div>
  );
}
