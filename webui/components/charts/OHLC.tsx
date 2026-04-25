"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import dayjs from "dayjs";

export interface OhlcBar {
  timestamp: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
}

interface OhlcChartProps {
  data: OhlcBar[];
  height?: number;
}

/**
 * Lightweight OHLC visualization.
 *
 * The full `react-financial-charts` candlestick canvas is heavy and finicky
 * with React 19 / Next 15 SSR; for the first pass we render a compact bar
 * chart of the high-low range coloured by direction. The dedicated
 * candlestick page can swap in the canvas-based component later.
 */
export function OhlcChart({ data, height = 360 }: OhlcChartProps) {
  const rows = data.map((b) => ({
    ts: typeof b.timestamp === "string" ? b.timestamp : String(b.timestamp),
    range: [b.low, b.high],
    open: b.open,
    close: b.close,
    body: [Math.min(b.open, b.close), Math.max(b.open, b.close)],
    rising: b.close >= b.open,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
        <CartesianGrid strokeOpacity={0.15} vertical={false} />
        <XAxis
          dataKey="ts"
          tick={{ fontSize: 11 }}
          minTickGap={32}
          tickFormatter={(v) => {
            const d = dayjs(v);
            return d.isValid() ? d.format("YYYY-MM-DD") : v;
          }}
        />
        <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
        <Tooltip
          labelFormatter={(v) => {
            const d = dayjs(v as string);
            return d.isValid() ? d.format("YYYY-MM-DD HH:mm") : String(v);
          }}
          formatter={(value, key) => {
            if (Array.isArray(value)) return [value.join(" – "), String(key)];
            return [value, String(key)];
          }}
        />
        <Bar dataKey="range" barSize={2} fill="#94a3b8" />
        <Bar dataKey="body" barSize={6}>
          {rows.map((r, i) => (
            <Cell key={i} fill={r.rising ? "#10b981" : "#ef4444"} />
          ))}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  );
}
