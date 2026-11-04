import type { ReactNode } from "react";
import { cx } from "../ui";

// Generic, defensive rendering for the eval report: unknown keys still show up sensibly.

const RATE_KEY =
  /(rate|recall|precision|accuracy|mrr|ndcg|hit|pct|ratio|share|faithful|grounded|correct|f1|coverage|claims|facts|answerable|_used|handled)/i;
const MS_KEY = /(^|_)(ms|latency)|_ms$|latency/i;

export function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function humanize(key: string): string {
  if (/[@]/.test(key)) return key; // keep metric names like recall@5 as-is
  return key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Numbers in 0..1 become percentages; *_ms / latency keys become milliseconds. */
export function formatNumber(key: string, n: number): string {
  if (MS_KEY.test(key)) return n >= 1000 ? `${(n / 1000).toFixed(2)} s` : `${Math.round(n)} ms`;
  const isRate = RATE_KEY.test(key) && !/(^|\.)checks\./.test(key);
  if (n >= 0 && n <= 1 && (!Number.isInteger(n) || isRate)) return `${(n * 100).toFixed(1)}%`;
  if (Number.isInteger(n)) return n.toLocaleString();
  return n.toFixed(3);
}

export function ReportValue({ name, value }: { name: string; value: unknown }): ReactNode {
  if (value === null || value === undefined) return <span className="text-ink-4">—</span>;
  if (typeof value === "number") {
    return <span className="font-mono tabular-nums">{formatNumber(name, value)}</span>;
  }
  if (typeof value === "boolean") return <span className="font-mono">{String(value)}</span>;
  if (typeof value === "string") return <span className="break-words">{value}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-ink-4">[]</span>;
    if (value.every(isRecord)) return <RecordTable rows={value} />;
    return <span className="break-words">{value.map((v) => String(v)).join(", ")}</span>;
  }
  if (isRecord(value)) return <KeyValueTable data={value} nested parentKey={name} />;
  return <span>{String(value)}</span>;
}

export function KeyValueTable({
  data,
  nested,
  omit = [],
  parentKey,
}: {
  data: Record<string, unknown>;
  nested?: boolean;
  omit?: string[];
  /** Section key, so e.g. `latency_ms: {p50: 820}` formats its values as milliseconds. */
  parentKey?: string;
}) {
  const entries = Object.entries(data).filter(([k]) => !omit.includes(k));
  if (entries.length === 0) return <span className="text-[13px] text-ink-4">No data</span>;
  return (
    <table className={cx("w-full text-[13px]", nested && "text-[12px]")}>
      <tbody className="divide-y divide-line">
        {entries.map(([k, v]) => (
          <tr key={k} className="align-top">
            <th className="w-1/3 py-1.5 pr-3 text-left font-normal text-ink-3">{humanize(k)}</th>
            <td className="py-1.5 text-ink">
              <ReportValue name={parentKey ? `${parentKey}.${k}` : k} value={v} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RecordTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[12px]">
        <thead className="text-ink-3">
          <tr>
            {columns.map((c) => (
              <th key={c} className="px-2 py-1.5 font-medium">
                {humanize(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r, i) => (
            <tr key={i} className="align-top">
              {columns.map((c) => (
                <td key={c} className="px-2 py-1.5">
                  <ReportValue name={c} value={r[c]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
