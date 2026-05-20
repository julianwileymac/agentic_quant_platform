import { useMemo } from "react";

import type { PortfolioMetricsResponse } from "@/lib/api/analytics";

/**
 * Compact grid of QuantStats-derived metrics. The payload comes from
 * ``POST /analytics/portfolio/metrics`` which already JSON-coerces
 * NaN/Inf to ``null`` so we can render dashes for missing values.
 */
type Props = {
  data: PortfolioMetricsResponse | null;
  loading?: boolean;
  error?: string | null;
};

type MetricRow = {
  label: string;
  key: keyof PortfolioMetricsResponse["metrics"];
  fmt?: (v: number) => string;
};

const PCT = (v: number) => `${(v * 100).toFixed(2)}%`;
const NUM = (v: number) => v.toFixed(3);

const ROWS: MetricRow[] = [
  { label: "Sharpe", key: "sharpe", fmt: NUM },
  { label: "Sortino", key: "sortino", fmt: NUM },
  { label: "CAGR", key: "cagr", fmt: PCT },
  { label: "Max Drawdown", key: "max_drawdown", fmt: PCT },
  { label: "Calmar", key: "calmar", fmt: NUM },
  { label: "Tail Ratio", key: "tail_ratio", fmt: NUM },
  { label: "Volatility (ann.)", key: "volatility", fmt: PCT },
  { label: "Skew", key: "skew", fmt: NUM },
  { label: "Kurtosis", key: "kurtosis", fmt: NUM },
  { label: "Win Rate", key: "win_rate", fmt: PCT },
  { label: "VaR (95%)", key: "value_at_risk", fmt: PCT },
  { label: "Expected Shortfall", key: "expected_shortfall", fmt: PCT },
];

export function TearSheetGrid({ data, loading, error }: Props) {
  const cards = useMemo(() => {
    if (!data) return [];
    return ROWS.map((row) => {
      const raw = data.metrics[row.key];
      const value =
        raw === null || raw === undefined
          ? "—"
          : row.fmt
            ? row.fmt(Number(raw))
            : String(raw);
      return { label: row.label, value, raw };
    });
  }, [data]);

  if (loading)
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        Loading metrics…
      </p>
    );
  if (error)
    return (
      <p className="text-xs text-[var(--neg-fg)]">{error}</p>
    );
  if (!data)
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        No metrics available.
      </p>
    );

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
      {cards.map((c) => (
        <div
          key={c.label}
          className="rounded-md border border-[var(--border-default)] bg-[var(--bg-card)] p-3"
        >
          <p className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">
            {c.label}
          </p>
          <p
            className="mt-1 text-base font-semibold"
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {c.value}
          </p>
        </div>
      ))}
    </div>
  );
}
