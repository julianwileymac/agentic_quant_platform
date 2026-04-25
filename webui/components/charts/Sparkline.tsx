"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";

interface SparklineProps {
  data: Array<{ x: number | string; y: number }>;
  color?: string;
  height?: number;
  showTooltip?: boolean;
}

export function Sparkline({ data, color = "#3b82f6", height = 40, showTooltip }: SparklineProps) {
  if (!data || data.length === 0) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", color: "#94a3b8", fontSize: 11 }}>
        no data
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
        <defs>
          <linearGradient id={`spark-${color}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.32} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={["auto", "auto"]} />
        <Area
          type="monotone"
          dataKey="y"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#spark-${color})`}
          dot={false}
          isAnimationActive={false}
        />
        {showTooltip ? <Tooltip /> : null}
      </AreaChart>
    </ResponsiveContainer>
  );
}
