import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { formatNumber, isRecord, tableHeadClass } from "./ReportValue";

/** Retrieval modes as rows, metrics as columns; the best value per metric is highlighted. */
export function RetrievalComparison({ modes }: { modes: Record<string, unknown> }) {
  const rows = Object.entries(modes).filter(([, v]) => isRecord(v)) as [
    string,
    Record<string, unknown>,
  ][];
  if (rows.length === 0) return <p className="text-[13px] text-muted-foreground/60">No retrieval modes.</p>;

  const metrics = Array.from(new Set(rows.flatMap(([, m]) => Object.keys(m))));
  const best: Record<string, number> = {};
  for (const metric of metrics) {
    if (metric === "n") continue;
    const values = rows.map(([, m]) => m[metric]).filter((v): v is number => typeof v === "number");
    if (values.length > 1) {
      best[metric] = /latency|_ms$/.test(metric) ? Math.min(...values) : Math.max(...values);
    }
  }

  return (
    <Table className="text-[13px]" data-testid="retrieval-comparison">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className={cn(tableHeadClass, "pl-0")}>Mode</TableHead>
          {metrics.map((m) => (
            <TableHead key={m} className={cn(tableHeadClass, "text-right")}>
              {m}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(([mode, values]) => (
          <TableRow key={mode}>
            <TableCell className="py-2.5 pl-0 font-mono text-[12px] font-medium text-foreground">
              {mode}
            </TableCell>
            {metrics.map((m) => {
              const v = values[m];
              const isBest = typeof v === "number" && best[m] === v;
              return (
                <TableCell
                  key={m}
                  className={cn(
                    "numeric py-2.5 text-right",
                    isBest ? "font-medium text-success" : "text-foreground/80",
                  )}
                >
                  {typeof v === "number" ? formatNumber(m, v) : v == null ? "—" : String(v)}
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
