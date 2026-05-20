import { describe, expect, it } from "vitest";

import { serializeStrategySpec } from "@/components/strategies/strategySerializer";
import type { FlowGraph } from "@/components/flow/types";

const GRAPH: FlowGraph = {
  domain: "strategy",
  version: 1,
  nodes: [
    {
      id: "s1",
      position: { x: 0, y: 0 },
      data: { kind: "Signal", label: "SMA cross", params: { kind: "sma_cross", fast: 10, slow: 30 } },
    },
    {
      id: "f1",
      position: { x: 0, y: 0 },
      data: { kind: "Factor", label: "Quality", params: { factor: "quality" } },
    },
    {
      id: "r1",
      position: { x: 0, y: 0 },
      data: { kind: "Risk", label: "Stop loss", params: { stop_pct: 0.05 } },
    },
    {
      id: "p1",
      position: { x: 0, y: 0 },
      data: { kind: "Portfolio", label: "Equal weight", params: {} },
    },
    {
      id: "e1",
      position: { x: 0, y: 0 },
      data: { kind: "Execution", label: "Alpaca", params: { broker: "alpaca" } },
    },
  ],
  edges: [
    { id: "e-s1-p1", source: "s1", target: "p1" },
    { id: "e-p1-e1", source: "p1", target: "e1" },
  ],
};

describe("strategy serializer", () => {
  it("groups nodes by their kind into the matching slot", () => {
    const spec = serializeStrategySpec(GRAPH, "test-strategy");
    expect(spec.name).toBe("test-strategy");
    expect(spec.signals).toHaveLength(1);
    expect(spec.signals[0]).toMatchObject({ id: "s1", kind: "sma_cross" });
    expect(spec.factors).toHaveLength(1);
    expect(spec.risk).toHaveLength(1);
    expect(spec.portfolio).toMatchObject({ id: "p1" });
    expect(spec.execution).toMatchObject({ id: "e1", broker: "alpaca" });
    expect(spec.wiring).toHaveLength(2);
  });

  it("returns empty slots for an empty graph", () => {
    const spec = serializeStrategySpec(
      { domain: "strategy", version: 1, nodes: [], edges: [] },
      "empty",
    );
    expect(spec.signals).toEqual([]);
    expect(spec.portfolio).toBeNull();
    expect(spec.execution).toBeNull();
  });
});
