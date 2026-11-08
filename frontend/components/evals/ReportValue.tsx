import type { ReactNode } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

// Generic, defensive rendering for the eval report: unknown keys still show up sensibly.

const RATE_KEY =
  /(rate|recall|precision|accuracy|mrr|ndcg|hit|pct|ratio|share|faithful|grounded|correct|f1|coverage|claims|facts|answerable|_used|handled)/i;
const MS_KEY = /(^|_)(ms|latency)|_ms$|latency/i;

/** Small-caps ledger header used by every eval table. */
export const tableHeadClass =
  "h-9 text-caption font-medium text-muted-foreground";

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
  if (value === null || value === undefined) return <span className="text-muted-foreground/60">—</span>;
  if (typeof value === "number") {
    return <span className="numeric">{formatNumber(name, value)}</span>;
  }
  if (typeof value === "boolean") return <span className="font-mono">{String(value)}</span>;
  if (typeof value === "string") return <span className="break-words">{value}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground/60">[]</span>;
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
  if (entries.length === 0) return <span className="text-ui text-muted-foreground/60">No data</span>;
  return (
    <Table className={cn("text-ui", nested && "text-meta")}>
      <TableBody>
        {entries.map(([k, v]) => (
          <TableRow key={k} className="align-top">
            <TableCell
              className={cn(
                "w-1/3 pr-3 pl-0 align-top whitespace-normal text-muted-foreground",
                nested ? "py-1" : "py-2",
              )}
            >
              {humanize(k)}
            </TableCell>
            <TableCell
              className={cn("pr-0 align-top whitespace-normal text-foreground", nested ? "py-1" : "py-2")}
            >
              <ReportValue name={parentKey ? `${parentKey}.${k}` : k} value={v} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function RecordTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
  return (
    <Table className="text-meta">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          {columns.map((c) => (
            <TableHead key={c} className={tableHeadClass}>
              {humanize(c)}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r, i) => (
          <TableRow key={i} className="align-top">
            {columns.map((c) => (
              <TableCell key={c} className="max-w-md min-w-24 align-top whitespace-normal">
                <ReportValue name={c} value={r[c]} />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
