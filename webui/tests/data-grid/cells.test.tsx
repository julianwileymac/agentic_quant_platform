import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  CurrencyCellFormatter,
  DateTimeCellFormatter,
  PercentCellFormatter,
  PnlCell,
  StatusBadgeCell,
} from "@/components/data-grid/cells";

describe("grid cell renderers", () => {
  it("StatusBadgeCell renders an Ant Tag for known statuses", () => {
    render(StatusBadgeCell({ value: "completed" } as never));
    expect(screen.getByText(/completed/i)).toBeInTheDocument();
  });

  it("PnlCell colours positive vs negative values", () => {
    const { rerender } = render(PnlCell({ value: 12 } as never));
    expect(screen.getByText("+12")).toBeInTheDocument();
    rerender(PnlCell({ value: -3.5 } as never));
    expect(screen.getByText(/-3\.5/)).toBeInTheDocument();
  });

  it("CurrencyCellFormatter formats dollars", () => {
    expect(CurrencyCellFormatter({ value: 1234 } as never)).toMatch(/\$1,234/);
    expect(CurrencyCellFormatter({ value: null } as never)).toBe("—");
  });

  it("PercentCellFormatter multiplies by 100", () => {
    expect(PercentCellFormatter({ value: 0.1 } as never)).toBe("10.00%");
  });

  it("DateTimeCellFormatter handles ISO and missing values", () => {
    expect(DateTimeCellFormatter({ value: "2024-04-01T12:00:00Z" } as never)).toMatch(
      /2024-04-01/,
    );
    expect(DateTimeCellFormatter({ value: null } as never)).toBe("—");
  });
});
