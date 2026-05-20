import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Palette } from "@/components/flow/Palette";
import { PALETTE_DRAG_MIME } from "@/components/flow/types";

const SECTIONS = [
  {
    title: "Source",
    items: [
      {
        kind: "Source",
        label: "yfinance",
        accent: "#10b981",
        defaultParams: { provider: "yahoo" },
      },
    ],
  },
  {
    title: "Sink",
    items: [{ kind: "Sink", label: "Iceberg", accent: "#f59e0b", defaultParams: { table: "" } }],
  },
];

describe("<Palette />", () => {
  it("renders every section title and tile label", () => {
    render(<Palette sections={SECTIONS} />);
    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("Sink")).toBeInTheDocument();
    expect(screen.getByText("yfinance")).toBeInTheDocument();
    expect(screen.getByText("Iceberg")).toBeInTheDocument();
  });

  it("dispatches a dragstart with the AQP MIME payload", () => {
    render(<Palette sections={SECTIONS} />);
    const tile = screen.getByText("yfinance").closest("button");
    expect(tile).toBeTruthy();

    const stored: Record<string, string> = {};
    const dataTransfer = {
      setData: (type: string, value: string) => {
        stored[type] = value;
      },
      getData: (type: string) => stored[type] ?? "",
      effectAllowed: "",
      types: [] as string[],
    };

    fireEvent.dragStart(tile!, { dataTransfer });
    expect(stored[PALETTE_DRAG_MIME]).toBeDefined();
    const payload = JSON.parse(stored[PALETTE_DRAG_MIME]!);
    expect(payload).toMatchObject({
      kind: "Source",
      label: "yfinance",
      accent: "#10b981",
      defaultParams: { provider: "yahoo" },
    });
  });
});
