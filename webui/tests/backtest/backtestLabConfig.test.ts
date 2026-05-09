import { describe, expect, it } from "vitest";

import { normaliseBacktestConfigShape } from "@/components/backtest/backtestLabConfig";

describe("normaliseBacktestConfigShape", () => {
  it("injects selected engine into backtest block", () => {
    const raw = {
      strategy: { class: "FrameworkAlgorithm" },
      backtest: { kwargs: { start: "2022-01-01", end: "2024-12-31" } },
    };

    const normalized = normaliseBacktestConfigShape(raw, "vectorbt-pro");

    expect(normalized).not.toBeNull();
    expect(normalized?.strategy).toEqual(raw.strategy);
    expect(normalized?.backtest).toEqual({
      kwargs: { start: "2022-01-01", end: "2024-12-31" },
      engine: "vectorbt-pro",
    });
  });

  it("returns null for incompatible shapes", () => {
    expect(normaliseBacktestConfigShape({}, "event")).toBeNull();
    expect(
      normaliseBacktestConfigShape(
        {
          strategy: { class: "FrameworkAlgorithm" },
        },
        "event",
      ),
    ).toBeNull();
  });
});
