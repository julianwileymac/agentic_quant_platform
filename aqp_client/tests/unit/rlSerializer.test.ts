import { describe, expect, it } from "vitest";

import { serializeRLExperiment } from "@/components/rl/rlSerializer";
import type { FlowGraph } from "@/components/flow/types";

const SAMPLE_GRAPH: FlowGraph = {
  domain: "rl",
  version: 1,
  nodes: [
    { id: "data", position: { x: 0, y: 0 }, data: { kind: "IcebergRLDataPipeline", params: {} } },
    { id: "env", position: { x: 0, y: 0 }, data: { kind: "StockTradingEnv", params: {} } },
    {
      id: "obs",
      position: { x: 0, y: 0 },
      data: { kind: "PortfolioStateBuilder", params: {} },
    },
    { id: "act", position: { x: 0, y: 0 }, data: { kind: "SoftmaxWeightsAction", params: {} } },
    { id: "rwd1", position: { x: 0, y: 0 }, data: { kind: "PnLTerm", params: { weight: 1.0 } } },
    {
      id: "rwd2",
      position: { x: 0, y: 0 },
      data: { kind: "DrawdownPenaltyTerm", params: { weight: 0.2 } },
    },
    {
      id: "term",
      position: { x: 0, y: 0 },
      data: { kind: "DrawdownTermination", params: { max_dd: 0.25 } },
    },
    {
      id: "ag",
      position: { x: 0, y: 0 },
      data: { kind: "SB3Adapter", params: { algo: "ppo" } },
    },
    {
      id: "exp",
      position: { x: 0, y: 0 },
      data: { kind: "BasicRLExperiment", params: {} },
    },
  ],
  edges: [],
};

describe("rl serializer", () => {
  it("collects every component into the matching spec slot", () => {
    const spec = serializeRLExperiment(SAMPLE_GRAPH, { name: "rl-test" });
    expect(spec.name).toBe("rl-test");
    expect(spec.env?.class).toBe("StockTradingEnv");
    expect(spec.observation?.spec?.class).toBe("PortfolioStateBuilder");
    expect(spec.action?.spec?.class).toBe("SoftmaxWeightsAction");
    expect(spec.data_pipeline?.spec?.class).toBe("IcebergRLDataPipeline");
    expect(spec.agent?.class).toBe("SB3Adapter");
    expect(spec.experiment?.class).toBe("BasicRLExperiment");
    expect(spec.terminations.specs).toHaveLength(1);
    expect(spec.terminations.specs[0]?.class).toBe("DrawdownTermination");
  });

  it("wraps reward terms in a CompositeReward", () => {
    const spec = serializeRLExperiment(SAMPLE_GRAPH, { name: "rl-test" });
    const reward = spec.reward?.spec;
    expect(reward?.class).toBe("CompositeReward");
    const terms = reward?.kwargs?.terms as Array<{ class: string }> | undefined;
    expect(terms).toBeDefined();
    expect(terms).toHaveLength(2);
    expect(terms?.map((t) => t.class).sort()).toEqual(["DrawdownPenaltyTerm", "PnLTerm"]);
  });

  it("returns null slots for missing components", () => {
    const spec = serializeRLExperiment(
      { domain: "rl", version: 1, nodes: [], edges: [] },
      { name: "empty" },
    );
    expect(spec.env).toBeNull();
    expect(spec.agent).toBeNull();
    expect(spec.terminations.specs).toEqual([]);
  });
});
