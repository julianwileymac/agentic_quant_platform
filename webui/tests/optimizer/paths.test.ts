import { describe, expect, it } from "vitest";

import { OPTIMIZER_LIST_PATH, optimizerDetailPath } from "@/components/optimizer/paths";

describe("optimizer API paths", () => {
  it("uses backend-compatible optimize base path", () => {
    expect(OPTIMIZER_LIST_PATH).toBe("/backtest/optimize");
  });

  it("builds encoded optimization detail path", () => {
    expect(optimizerDetailPath("run-123")).toBe("/backtest/optimize/run-123");
    expect(optimizerDetailPath("run/with/slash")).toBe(
      "/backtest/optimize/run%2Fwith%2Fslash",
    );
  });
});
