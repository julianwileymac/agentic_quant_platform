import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Numeric } from "@/components/common/Numeric";

describe("<Numeric />", () => {
  it("renders an em-dash for non-finite values", () => {
    render(<Numeric value={Number.NaN} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("colours negative values red and positive values green", () => {
    const { rerender } = render(<Numeric value={-1.23} />);
    const node = screen.getByText("-1.23");
    expect(node).toHaveStyle({ color: "var(--neg-fg)" });
    rerender(<Numeric value={5.67} />);
    expect(screen.getByText("5.67")).toHaveStyle({ color: "var(--pos-fg)" });
  });

  it("renders zero in the neutral colour by default", () => {
    render(<Numeric value={0} />);
    expect(screen.getByText("0.00")).toHaveStyle({ color: "var(--text-primary)" });
  });

  it("formats currency for kind=money", () => {
    render(<Numeric value={1234.5} kind="money" digits={0} />);
    expect(screen.getByText("$1,235")).toBeInTheDocument();
  });

  it("formats percentages with a leading sign for positive values", () => {
    render(<Numeric value={0.025} kind="percent" digits={2} />);
    expect(screen.getByText("+2.50%")).toBeInTheDocument();
  });

  it("emits the data-numeric attribute so global tabular CSS applies", () => {
    render(<Numeric value={1} />);
    expect(screen.getByText("1.00")).toHaveAttribute("data-numeric", "true");
  });
});
