import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PortfolioRollingResponse } from "@/lib/api/analytics";

type Props = {
  data: PortfolioRollingResponse | null;
  loading?: boolean;
  error?: string | null;
};

/** Underwater (drawdown) area chart. Negative-only area, red fill. */
export function UnderwaterPanel({ data, loading, error }: Props) {
  const series = useMemo(() => {
    if (!data) return [];
    return data.underwater
      .filter((p) => p.v !== null && p.v !== undefined)
      .map((p) => ({ t: p.t, v: p.v ?? 0 }));
  }, [data]);

  if (loading)
    return (
      <p className="text-xs text-[var(--text-secondary)]">Loading…</p>
    );
  if (error)
    return <p className="text-xs text-[var(--neg-fg)]">{error}</p>;
  if (!series.length)
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        No drawdown data yet.
      </p>
    );

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={series} margin={{ top: 8, right: 12, bottom: 4, left: 12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" />
          <XAxis
            dataKey="t"
            tick={{ fontSize: 10, fill: "var(--text-secondary)" }}
            minTickGap={32}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--text-secondary)" }}
            tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
            width={48}
          />
          <Tooltip
            formatter={(v: number | string) => {
              const n = typeof v === "number" ? v : Number(v);
              return [`${(n * 100).toFixed(2)}%`, "Drawdown"];
            }}
          />
          <Area
            type="monotone"
            dataKey="v"
            stroke="var(--neg-fg)"
            fill="var(--neg-fg)"
            fillOpacity={0.18}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
