"use client";

import { useState } from "react";
import { Segmented, cx } from "../ui";

export type ModeMetrics = Record<string, number>;

const MODE_LABELS: Record<string, { name: string; detail: string }> = {
  dense: { name: "Dense", detail: "bge-small · cosine" },
  lexical: { name: "Lexical", detail: "Postgres full-text" },
  hybrid: { name: "Hybrid", detail: "dense + lexical · RRF" },
  hybrid_rerank: { name: "Hybrid + rerank", detail: "cross-encoder on top 20" },
};

const METRICS = [
  { value: "hit@1", label: "Hit@1" },
  { value: "hit@3", label: "Hit@3" },
  { value: "mrr", label: "MRR" },
] as const;
type Metric = (typeof METRICS)[number]["value"];

const TICKS = [0, 0.25, 0.5, 0.75, 1];

/**
 * Horizontal bars, one per retrieval mode, on a zero baseline. A single series, so no legend:
 * the default mode is the one highlighted series (accent); the rest stay neutral ink.
 * Hover (or focus) a row for every metric of that mode; a table copy is available to screen readers.
 */
export function ModeChart({
  modes,
  defaultMode,
}: {
  modes: Record<string, ModeMetrics>;
  defaultMode?: string;
}) {
  const [metric, setMetric] = useState<Metric>("hit@1");
  const [hover, setHover] = useState<string | null>(null);
  const rows = Object.entries(modes);

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <Segmented
          label="Metric"
          value={metric}
          onChange={setMetric}
          options={METRICS.map((m) => ({ value: m.value, label: m.label }))}
        />
        <div className="flex items-center gap-2 text-[12px] text-ink-3">
          <span className="h-2 w-2 rounded-[2px] bg-accent" aria-hidden />
          default mode
        </div>
      </div>

      <div className="relative" aria-hidden>
        {/* recessive grid */}
        <div className="pointer-events-none absolute inset-y-0 right-14 left-[9.5rem] sm:left-[11.5rem]">
          {TICKS.map((t) => (
            <div
              key={t}
              className="absolute inset-y-0 border-l border-dashed border-line"
              style={{ left: `${t * 100}%` }}
            />
          ))}
        </div>

        <div className="relative space-y-1">
          {rows.map(([mode, m]) => {
            const v = m[metric] ?? 0;
            const isDefault = mode === defaultMode;
            const label = MODE_LABELS[mode] ?? { name: mode, detail: "" };
            return (
              <div
                key={mode}
                tabIndex={0}
                onMouseEnter={() => setHover(mode)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(mode)}
                onBlur={() => setHover(null)}
                className={cx(
                  "relative flex items-center rounded-lg py-2 outline-none",
                  hover === mode && "bg-paper",
                )}
              >
                <div className="w-[9.5rem] shrink-0 pl-2 sm:w-[11.5rem]">
                  <div className="text-[13px] font-medium text-ink">{label.name}</div>
                  <div className="hidden text-[11.5px] text-ink-3 sm:block">{label.detail}</div>
                </div>
                <div className="relative h-3 flex-1">
                  <div
                    className={cx(
                      "absolute inset-y-0 left-0 rounded-r-[4px] transition-[width] duration-500 ease-out",
                      isDefault ? "bg-accent" : "bg-ink-4/70",
                    )}
                    style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }}
                  />
                </div>
                <div className="w-14 shrink-0 pr-2 text-right font-mono text-[12.5px] text-ink tabular-nums">
                  {metric === "mrr" ? v.toFixed(3) : `${(v * 100).toFixed(1)}%`}
                </div>

                {hover === mode && (
                  <div className="absolute top-full right-2 z-10 mt-1 w-56 animate-rise rounded-lg border border-line bg-surface p-3 text-[12px] shadow-pop">
                    <div className="mb-2 font-medium text-ink">{label.name}</div>
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
                      {Object.entries(m).map(([k, val]) => (
                        <div key={k} className="contents">
                          <dt className="text-ink-3">{k}</dt>
                          <dd className="text-right font-mono text-ink tabular-nums">
                            {k === "n" ? val : val.toFixed(3)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-2 flex pr-14 pl-[9.5rem] font-mono text-[10.5px] text-ink-4 sm:pl-[11.5rem]">
          <div className="relative h-4 flex-1">
            {TICKS.map((t) => (
              <span
                key={t}
                className="absolute -translate-x-1/2 tabular-nums"
                style={{ left: `${t * 100}%` }}
              >
                {metric === "mrr" ? t.toFixed(2) : `${t * 100}%`}
              </span>
            ))}
          </div>
        </div>
      </div>

      <table className="sr-only">
        <caption>Retrieval quality by mode</caption>
        <thead>
          <tr>
            <th>Mode</th>
            <th>hit@1</th>
            <th>hit@3</th>
            <th>MRR</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([mode, m]) => (
            <tr key={mode}>
              <td>{mode}</td>
              <td>{m["hit@1"]}</td>
              <td>{m["hit@3"]}</td>
              <td>{m.mrr}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
