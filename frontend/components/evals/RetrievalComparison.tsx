import { cx } from "../ui";
import { formatNumber, isRecord } from "./ReportValue";

/** Retrieval modes as rows, metrics as columns; the best value per metric is highlighted. */
export function RetrievalComparison({ modes }: { modes: Record<string, unknown> }) {
  const rows = Object.entries(modes).filter(([, v]) => isRecord(v)) as [
    string,
    Record<string, unknown>,
  ][];
  if (rows.length === 0) return <p className="text-[13px] text-ink-4">No retrieval modes.</p>;

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
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px]" data-testid="retrieval-comparison">
        <thead className="border-b border-line text-[12px] text-ink-3">
          <tr>
            <th className="py-2 pr-4 font-medium">Mode</th>
            {metrics.map((m) => (
              <th key={m} className="px-3 py-2 text-right font-medium">
                {m}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map(([mode, values]) => (
            <tr key={mode}>
              <td className="py-2 pr-4 font-mono text-[12px] font-medium text-ink">{mode}</td>
              {metrics.map((m) => {
                const v = values[m];
                const isBest = typeof v === "number" && best[m] === v;
                return (
                  <td
                    key={m}
                    className={cx(
                      "px-3 py-2 text-right font-mono tabular-nums",
                      isBest ? "font-semibold text-ok" : "text-ink-2",
                    )}
                  >
                    {typeof v === "number" ? formatNumber(m, v) : v == null ? "—" : String(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
