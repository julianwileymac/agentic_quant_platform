import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";

describe("<MetricsGrid />", () => {
  const metrics: Metric[] = [
    { label: "Sharpe", value: 1.45, kind: "decimal" },
    { label: "Max DD", value: -0.12, kind: "percent", tone: "force-neg" },
    { label: "Total PnL", value: 12_345, kind: "money", digits: 0, signed: true },
    { label: "Sortino", value: null, kind: "decimal" },
  ];

  it("renders one cell per metric with the supplied label", () => {
    render(<MetricsGrid metrics={metrics} columns={4} />);
    expect(screen.getByText("Sharpe")).toBeInTheDocument();
    expect(screen.getByText("Max DD")).toBeInTheDocument();
    expect(screen.getByText("Total PnL")).toBeInTheDocument();
    expect(screen.getByText("Sortino")).toBeInTheDocument();
  });

  it("colours negatives red and positives green automatically", () => {
    render(<MetricsGrid metrics={metrics} columns={4} />);
    expect(screen.getByText("1.45")).toHaveStyle({ color: "var(--pos-fg)" });
    // Percent values render with the +/- sign in the formatted string.
    const negEl = screen.getByText("-12.00%");
    expect(negEl).toHaveStyle({ color: "var(--neg-fg)" });
  });

  it("falls back to em-dash for null / undefined values", () => {
    render(<MetricsGrid metrics={metrics} columns={4} />);
    // The Sortino metric has value=null, the Numeric primitive shows '—'.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
  });
});
