"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";

import { cn } from "@/lib/cn";

interface MetricSparklineProps {
  /** Array of data points; supplied as numbers. */
  data: number[];
  /** Label shown above the sparkline. */
  label?: string;
  /** Trailing value formatted into the top-right corner. */
  value?: string;
  /** Color tone. */
  tone?: "primary" | "secondary" | "tertiary" | "warn" | "neg";
  /** Total height in pixels. */
  height?: number;
  /** When true, shows a small +/- delta tag between start and end. */
  showDelta?: boolean;
  className?: string;
}

const TONE_COLORS = {
  primary: { stroke: "#60a5fa", fill: "#1677ff" },
  secondary: { stroke: "#a78bfa", fill: "#722ed1" },
  tertiary: { stroke: "#34d399", fill: "#10b981" },
  warn: { stroke: "#fbbf24", fill: "#f59e0b" },
  neg: { stroke: "#f87171", fill: "#ef4444" },
} as const;

/**
 * Mini area chart for marketing pages — RL convergence curves, illustrative
 * equity curves, Sharpe distributions, etc. Data is illustrative, not live.
 */
export function MetricSparkline({
  data,
  label,
  value,
  tone = "primary",
  height = 96,
  showDelta = true,
  className,
}: MetricSparklineProps) {
  const colors = TONE_COLORS[tone];
  const series = data.map((y, x) => ({ x, y }));
  const first = data[0] ?? 0;
  const last = data[data.length - 1] ?? 0;
  const delta = last - first;
  const deltaPct = first !== 0 ? (delta / Math.abs(first)) * 100 : 0;
  const positive = delta >= 0;
  const gradientId = `spark-${tone}-${Math.round(Math.random() * 10000)}`;

  return (
    <div
      className={cn(
        "rounded-lg p-4",
        className,
      )}
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(var(--glass-blur))",
      }}
    >
      {(label || value || showDelta) && (
        <div className="mb-2 flex items-baseline justify-between">
          {label ? (
            <span
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}
            >
              {label}
            </span>
          ) : (
            <span />
          )}
          <div className="flex items-baseline gap-2">
            {value ? (
              <span
                className="text-base font-bold tabular"
                style={{ color: "var(--text-primary)" }}
              >
                {value}
              </span>
            ) : null}
            {showDelta ? (
              <span
                className="rounded px-1.5 py-0.5 text-[10px] font-bold tabular"
                style={{
                  background: positive
                    ? "rgba(16,185,129,0.15)"
                    : "rgba(239,68,68,0.15)",
                  color: positive ? "var(--pos-fg)" : "var(--neg-fg)",
                }}
              >
                {positive ? "+" : ""}
                {deltaPct.toFixed(1)}%
              </span>
            ) : null}
          </div>
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart
          data={series}
          margin={{ top: 4, right: 0, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colors.fill} stopOpacity={0.4} />
              <stop offset="100%" stopColor={colors.fill} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Tooltip
            cursor={false}
            contentStyle={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-default)",
              borderRadius: 6,
              fontSize: 11,
            }}
            labelStyle={{ display: "none" }}
            formatter={(v: number) => [v.toFixed(2), ""]}
            separator=""
          />
          <Area
            type="monotone"
            dataKey="y"
            stroke={colors.stroke}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            isAnimationActive
            animationDuration={1200}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
