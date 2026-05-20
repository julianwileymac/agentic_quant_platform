import { render, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PayoffChart } from "@/components/options/PayoffChart";

describe("<PayoffChart />", () => {
  it("renders a payoff path SVG with K and F markers", async () => {
    const { container } = render(
      <PayoffChart forward={100} strike={100} isCall={true} premium={5} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    await waitFor(() => {
      expect(svg!.querySelector("path")).not.toBeNull();
    });
    const text = svg!.textContent ?? "";
    expect(text).toContain("K = 100.00");
    expect(text).toContain("F = 100.00");
  });

  it("renders a put payoff without crashing", () => {
    const { container } = render(<PayoffChart forward={100} strike={110} isCall={false} />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
  });
});
