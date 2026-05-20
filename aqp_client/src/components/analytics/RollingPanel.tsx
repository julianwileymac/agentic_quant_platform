import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PortfolioRollingResponse } from "@/lib/api/analytics";

type Props = {
  data: PortfolioRollingResponse | null;
  panel: "sharpe" | "vol";
  loading?: boolean;
  error?: string | null;
};

/** Rolling Sharpe / rolling volatility chart (recharts; already in deps). */
export function RollingPanel({ data, panel, loading, error }: Props) {
  const series = useMemo(() => {
    if (!data) return [];
    const source = panel === "sharpe" ? data.rolling_sharpe : data.rolling_vol;
    return source
      .filter((p) => p.v !== null && p.v !== undefined)
      .map((p) => ({ t: p.t, v: p.v ?? 0 }));
  }, [data, panel]);

  if (loading)
    return (
      <p className="text-xs text-[var(--text-secondary)]">Loading…</p>
    );
  if (error)
    return <p className="text-xs text-[var(--neg-fg)]">{error}</p>;
  if (!series.length)
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        No rolling data yet.
      </p>
    );

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series} margin={{ top: 8, right: 12, bottom: 4, left: 12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" />
          <XAxis
            dataKey="t"
            tick={{ fontSize: 10, fill: "var(--text-secondary)" }}
            minTickGap={32}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--text-secondary)" }}
            width={48}
          />
          <Tooltip />
          {panel === "sharpe" ? (
            <ReferenceLine y={0} stroke="var(--border-muted)" />
          ) : null}
          <Line
            type="monotone"
            dataKey="v"
            stroke="var(--pos-fg)"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
