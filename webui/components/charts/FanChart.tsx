"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface FanPoint {
  step: number | string;
  median: number;
  p10?: number;
  p90?: number;
  p25?: number;
  p75?: number;
}

interface FanChartProps {
  data: FanPoint[];
  height?: number;
}

export function FanChart({ data, height = 280 }: FanChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
        <CartesianGrid strokeOpacity={0.15} vertical={false} />
        <XAxis dataKey="step" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
        <Tooltip />
        {data[0]?.p10 !== undefined ? (
          <Area
            type="monotone"
            dataKey="p90"
            stroke="transparent"
            fill="#3b82f6"
            fillOpacity={0.1}
          />
        ) : null}
        {data[0]?.p25 !== undefined ? (
          <Area
            type="monotone"
            dataKey="p75"
            stroke="transparent"
            fill="#3b82f6"
            fillOpacity={0.18}
          />
        ) : null}
        <Line type="monotone" dataKey="median" stroke="#3b82f6" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
