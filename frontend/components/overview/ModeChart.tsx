"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import { Segmented } from "../ui";

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

type Row = { mode: string; name: string; value: number; metrics: ModeMetrics; isDefault: boolean };

function formatValue(metric: Metric, v: number): string {
  return metric === "mrr" ? v.toFixed(3) : `${(v * 100).toFixed(1)}%`;
}

/**
 * Horizontal bars, one per retrieval mode, on a zero baseline. A single series, so no legend:
 * the default mode is the one highlighted bar (chart-1); the rest use the light chart-3.
 * Hover a bar for every metric of that mode; a table copy is available to screen readers.
 */
export function ModeChart({
  modes,
  defaultMode,
}: {
  modes: Record<string, ModeMetrics>;
  defaultMode?: string;
}) {
  const [metric, setMetric] = useState<Metric>("hit@1");
  const entries = Object.entries(modes);
  const metricLabel = METRICS.find((m) => m.value === metric)?.label ?? metric;

  const data: Row[] = entries.map(([mode, m]) => ({
    mode,
    name: MODE_LABELS[mode]?.name ?? mode,
    value: Math.max(0, Math.min(1, m[metric] ?? 0)),
    metrics: m,
    isDefault: mode === defaultMode,
  }));

  const config = {
    value: { label: metricLabel, color: "var(--chart-1)" },
  } satisfies ChartConfig;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Segmented
          label="Metric"
          value={metric}
          onChange={setMetric}
          options={METRICS.map((m) => ({ value: m.value, label: m.label }))}
        />
        <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
          <span className="h-2 w-2 rounded-[2px] bg-chart-1" aria-hidden />
          default mode
        </div>
      </div>

      <div aria-hidden>
        <ChartContainer config={config} className="aspect-auto h-[240px] w-full">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 56, bottom: 0, left: 4 }}
            barCategoryGap="28%"
            accessibilityLayer={false}
          >
            <CartesianGrid horizontal={false} strokeDasharray="3 3" />
            <XAxis
              type="number"
              domain={[0, 1]}
              ticks={TICKS}
              tickLine={false}
              axisLine={false}
              tickMargin={6}
              tickFormatter={(t: number) => (metric === "mrr" ? t.toFixed(2) : `${t * 100}%`)}
              className="font-mono"
            />
            <YAxis
              type="category"
              dataKey="name"
              width={120}
              tickLine={false}
              axisLine={false}
              tickMargin={8}
            />
            <ChartTooltip
              cursor={{ fill: "var(--muted)" }}
              content={({ active, payload }) => {
                const row = active ? (payload?.[0]?.payload as Row | undefined) : undefined;
                return row ? <ModeTooltip row={row} /> : null;
              }}
            />
            <Bar dataKey="value" radius={4} isAnimationActive>
              {data.map((d) => (
                <Cell key={d.mode} fill={d.isDefault ? "var(--chart-1)" : "var(--chart-3)"} />
              ))}
              <LabelList
                dataKey="value"
                position="right"
                offset={8}
                className="fill-foreground font-mono"
                fontSize={12}
                formatter={(v: unknown) => formatValue(metric, Number(v))}
              />
            </Bar>
          </BarChart>
        </ChartContainer>
      </div>

      <table className="sr-only">
        <caption>Hit@1, hit@3 and MRR for each retrieval mode</caption>
        <thead>
          <tr>
            <th>Mode</th>
            <th>hit@1</th>
            <th>hit@3</th>
            <th>MRR</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([mode, m]) => (
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

function ModeTooltip({ row }: { row: Row }) {
  const detail = MODE_LABELS[row.mode]?.detail;
  return (
    <div className="grid min-w-48 gap-2 rounded-md border bg-popover px-3 py-2.5 text-[12px] text-popover-foreground shadow-card">
      <div>
        <div className="font-medium">{row.name}</div>
        {detail && <div className="text-[11px] text-muted-foreground">{detail}</div>}
      </div>
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
        {Object.entries(row.metrics).map(([k, val]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="numeric text-right text-foreground">
              {k === "n" ? val : val.toFixed(3)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
