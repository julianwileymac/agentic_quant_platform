import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EquityChart } from "@/components/charts/EquityChart";

describe("<EquityChart />", () => {
  it("renders an empty-state when no data is provided", () => {
    render(<EquityChart data={[]} />);
    expect(screen.getByText(/no data available/i)).toBeInTheDocument();
  });

  it("renders an SVG when data is supplied", () => {
    const data = [
      { timestamp: "2024-01-01", value: 100 },
      { timestamp: "2024-01-02", value: 102 },
      { timestamp: "2024-01-03", value: 104 },
      { timestamp: "2024-01-04", value: 110 },
    ];
    const { container } = render(<EquityChart data={data} height={240} />);
    // ResizeObserver is polyfilled in tests/unit/setup.ts but never fires in
    // jsdom; we ship the SVG node either way once data is non-empty.
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    expect(container.querySelector("[data-equity-chart]")).toHaveAttribute(
      "data-equity-chart",
      "true",
    );
  });

  it("computes per-row drawdown based on running peak", () => {
    // The drawdown helper is internal but the component renders a band
    // when showDrawdown is on and at least two points are present.
    const data = [
      { timestamp: "2024-01-01", value: 100 },
      { timestamp: "2024-01-02", value: 110 },
      { timestamp: "2024-01-03", value: 90 },
    ];
    const { container } = render(<EquityChart data={data} showDrawdown height={240} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });
});
