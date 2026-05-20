import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DistributionOverlayResponse } from "@/lib/api/analytics";

type Props = {
  data: DistributionOverlayResponse | null;
  loading?: boolean;
  error?: string | null;
};

export function DistributionOverlay({ data, loading, error }: Props) {
  const series = useMemo(() => {
    if (!data) return [];
    return data.bins.map((bin, i) => ({
      bin: bin === null ? `b${i}` : (bin as number).toFixed(3),
      actual: data.actual[i] ?? 0,
      predicted: data.predicted[i] ?? 0,
    }));
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
        No distribution data yet.
      </p>
    );

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={series} margin={{ top: 8, right: 12, bottom: 4, left: 12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-muted)" />
          <XAxis
            dataKey="bin"
            tick={{ fontSize: 10, fill: "var(--text-secondary)" }}
            minTickGap={28}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--text-secondary)" }}
            width={36}
          />
          <Tooltip />
          <Legend />
          <Bar dataKey="actual" fill="var(--pos-fg)" opacity={0.65} />
          <Bar dataKey="predicted" fill="var(--accent-fg)" opacity={0.65} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
