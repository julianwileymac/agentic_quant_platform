import * as d3 from "d3";
import { useMemo } from "react";

import { cn } from "@/lib/utils";

export interface HeatmapPoint {
  paramA: string | number;
  paramB: string | number;
  metric: number;
}

interface HeatmapProps {
  points: HeatmapPoint[];
  paramALabel: string;
  paramBLabel: string;
  metricLabel: string;
  className?: string;
}

/**
 * CSS-grid heatmap of (paramA × paramB) → metric. Pure-CSS — no D3
 * scale/draw cycle — to keep the param-sweep dashboard responsive on
 * grids of 100+ cells. D3 is only used for the colour-interpolation.
 */
export function Heatmap({ points, paramALabel, paramBLabel, metricLabel, className }: HeatmapProps) {
  const { rows, cols, byKey, range } = useMemo(() => {
    const rowSet = new Map<string, string | number>();
    const colSet = new Map<string, string | number>();
    const m = new Map<string, number>();
    for (const p of points) {
      rowSet.set(String(p.paramA), p.paramA);
      colSet.set(String(p.paramB), p.paramB);
      m.set(`${p.paramA}|${p.paramB}`, p.metric);
    }
    const rowsArr = Array.from(rowSet.values());
    const colsArr = Array.from(colSet.values());
    const metrics = points.map((p) => p.metric);
    const lo = d3.min(metrics) ?? 0;
    const hi = d3.max(metrics) ?? 1;
    return { rows: rowsArr, cols: colsArr, byKey: m, range: [lo, hi] as [number, number] };
  }, [points]);

  const color = useMemo(() => d3.scaleSequential(d3.interpolateRdYlGn).domain(range), [range]);

  if (points.length === 0) {
    return (
      <div className="flex h-full items-center justify-center rounded-md border border-dashed border-[var(--border-default)] p-6 text-xs text-[var(--text-secondary)]">
        No completed sweeps yet.
      </div>
    );
  }

  return (
    <div className={cn("relative overflow-auto", className)}>
      <table className="border-collapse text-[10px]">
        <thead>
          <tr>
            <th className="sticky left-0 top-0 z-20 border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1 text-left">
              <span className="text-[var(--text-secondary)]">
                {paramALabel} ↓ / {paramBLabel} →
              </span>
            </th>
            {cols.map((c) => (
              <th
                key={String(c)}
                className="sticky top-0 z-10 border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1 text-center font-mono"
              >
                {String(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r)}>
              <th className="sticky left-0 z-10 border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1 text-right font-mono">
                {String(r)}
              </th>
              {cols.map((c) => {
                const m = byKey.get(`${r}|${c}`);
                if (m === undefined) {
                  return (
                    <td
                      key={String(c)}
                      className="border border-[var(--border-default)] bg-[var(--bg-app)] px-2 py-1 text-[var(--text-muted)]"
                      title="no data"
                    >
                      ·
                    </td>
                  );
                }
                const bg = color(m);
                return (
                  <td
                    key={String(c)}
                    style={{ backgroundColor: bg }}
                    className="border border-[var(--border-default)] px-2 py-1 text-center font-mono text-black"
                    title={`${paramALabel}=${r} · ${paramBLabel}=${c} · ${metricLabel}=${m.toFixed(3)}`}
                  >
                    {m.toFixed(2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-2 text-[10px] text-[var(--text-secondary)]">
        <span>Range: {range[0].toFixed(3)} → {range[1].toFixed(3)}</span>
        <span>·</span>
        <span>Metric: {metricLabel}</span>
      </div>
    </div>
  );
}
