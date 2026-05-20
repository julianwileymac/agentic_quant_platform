import { useMemo } from "react";

import type { PortfolioRollingResponse } from "@/lib/api/analytics";

type Props = {
  data: PortfolioRollingResponse | null;
  topN?: number;
};

type DrawdownPeriod = {
  start: string;
  end: string;
  peak: string;
  trough: number;
  recovery: string | null;
  duration_days: number;
};

/** Identify contiguous underwater periods + their depths. */
function extractDrawdownPeriods(
  series: PortfolioRollingResponse["underwater"],
): DrawdownPeriod[] {
  if (!series.length) return [];
  const periods: DrawdownPeriod[] = [];
  let cur: { start: string; trough: number; troughT: string } | null = null;
  for (const p of series) {
    const v = p.v ?? 0;
    if (v < -0.0001) {
      if (!cur) {
        cur = { start: p.t, trough: v, troughT: p.t };
      } else if (v < cur.trough) {
        cur.trough = v;
        cur.troughT = p.t;
      }
    } else if (cur) {
      const start = new Date(cur.start).getTime();
      const end = new Date(p.t).getTime();
      periods.push({
        start: cur.start,
        end: p.t,
        peak: cur.troughT,
        trough: cur.trough,
        recovery: p.t,
        duration_days: Math.round((end - start) / (1000 * 60 * 60 * 24)),
      });
      cur = null;
    }
  }
  if (cur) {
    const last = series[series.length - 1];
    if (last) {
      const start = new Date(cur.start).getTime();
      const end = new Date(last.t).getTime();
      periods.push({
        start: cur.start,
        end: last.t,
        peak: cur.troughT,
        trough: cur.trough,
        recovery: null,
        duration_days: Math.round((end - start) / (1000 * 60 * 60 * 24)),
      });
    }
  }
  return periods;
}

export function DrawdownTable({ data, topN = 10 }: Props) {
  const periods = useMemo(() => {
    if (!data) return [];
    return extractDrawdownPeriods(data.underwater)
      .sort((a, b) => a.trough - b.trough)
      .slice(0, Math.max(1, topN));
  }, [data, topN]);

  if (!data || !periods.length)
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        No drawdown periods to show.
      </p>
    );

  return (
    <div className="overflow-x-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-card)]">
      <table className="w-full text-xs" style={{ fontVariantNumeric: "tabular-nums" }}>
        <thead className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">
          <tr>
            <th className="px-2 py-1.5 text-left">Start</th>
            <th className="px-2 py-1.5 text-left">Trough</th>
            <th className="px-2 py-1.5 text-right">Depth</th>
            <th className="px-2 py-1.5 text-left">Recovery</th>
            <th className="px-2 py-1.5 text-right">Days</th>
          </tr>
        </thead>
        <tbody>
          {periods.map((p, i) => (
            <tr
              key={`${p.start}-${i}`}
              className="border-t border-[var(--border-muted)]"
            >
              <td className="px-2 py-1">{p.start.slice(0, 10)}</td>
              <td className="px-2 py-1">{p.peak.slice(0, 10)}</td>
              <td
                className="px-2 py-1 text-right text-[var(--neg-fg)]"
                title={`${p.trough}`}
              >
                {(p.trough * 100).toFixed(2)}%
              </td>
              <td className="px-2 py-1">
                {p.recovery ? p.recovery.slice(0, 10) : "—"}
              </td>
              <td className="px-2 py-1 text-right">{p.duration_days}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
