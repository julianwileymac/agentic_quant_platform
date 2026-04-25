"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import dayjs from "dayjs";

export interface EquityPoint {
  timestamp: string | number;
  value: number;
}

interface EquityChartProps {
  data: EquityPoint[];
  height?: number;
  benchmark?: EquityPoint[];
}

export function EquityChart({ data, height = 320, benchmark }: EquityChartProps) {
  const merged = data.map((d, i) => ({
    ts: typeof d.timestamp === "string" ? d.timestamp : String(d.timestamp),
    value: d.value,
    benchmark: benchmark?.[i]?.value ?? null,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={merged} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
        <CartesianGrid strokeOpacity={0.15} vertical={false} />
        <XAxis
          dataKey="ts"
          tick={{ fontSize: 11 }}
          tickFormatter={(v) => {
            const d = dayjs(v);
            return d.isValid() ? d.format("MMM YY") : v;
          }}
          minTickGap={32}
        />
        <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
        <Tooltip
          labelFormatter={(v) => {
            const d = dayjs(v as string);
            return d.isValid() ? d.format("YYYY-MM-DD") : String(v);
          }}
          formatter={(val) =>
            typeof val === "number"
              ? val.toLocaleString(undefined, { maximumFractionDigits: 2 })
              : (val as string)
          }
        />
        <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} dot={false} />
        {benchmark ? (
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke="#94a3b8"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            dot={false}
          />
        ) : null}
      </LineChart>
    </ResponsiveContainer>
  );
}
