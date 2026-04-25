import { describe, expect, it } from "vitest";

import {
  serializeAgentCrew,
  serializeDataPipeline,
  serializeStrategy,
} from "@/components/flow/serializers";
import type { FlowGraph } from "@/components/flow/types";

const graph: FlowGraph = {
  domain: "agent",
  version: 1,
  nodes: [
    {
      id: "llm",
      type: "aqp",
      position: { x: 0, y: 0 },
      data: { kind: "LLM", label: "Quick", params: { tier: "quick" } },
    },
    {
      id: "agent",
      type: "aqp",
      position: { x: 100, y: 0 },
      data: { kind: "Agent", label: "Researcher", params: { role: "researcher" } },
    },
  ],
  edges: [{ id: "e", source: "llm", target: "agent" }],
};

describe("flow serializers", () => {
  it("serializeAgentCrew maps nodes + edges + prompt", () => {
    const out = serializeAgentCrew(graph, "go");
    expect(out.prompt).toBe("go");
    expect(out.config.nodes).toHaveLength(2);
    expect(out.config.edges).toEqual([{ source: "llm", target: "agent" }]);
  });

  it("serializeDataPipeline derives dependencies from edges", () => {
    const data: FlowGraph = {
      domain: "data",
      version: 1,
      nodes: [
        { id: "src", type: "aqp", position: { x: 0, y: 0 }, data: { kind: "Source" } },
        { id: "tx", type: "aqp", position: { x: 0, y: 0 }, data: { kind: "Transform" } },
      ],
      edges: [{ id: "e", source: "src", target: "tx" }],
    };
    const out = serializeDataPipeline(data);
    expect(out.jobs.find((j) => j.id === "tx")?.dependencies).toEqual(["src"]);
    expect(out.jobs.find((j) => j.id === "src")?.dependencies).toEqual([]);
  });

  it("serializeStrategy emits valid YAML scaffolding", () => {
    const strat: FlowGraph = {
      domain: "strategy",
      version: 1,
      nodes: [
        {
          id: "sig",
          type: "aqp",
          position: { x: 0, y: 0 },
          data: { kind: "Signal", params: { kind: "sma_cross", fast: 10, slow: 30 } },
        },
        {
          id: "size",
          type: "aqp",
          position: { x: 100, y: 0 },
          data: { kind: "Sizing", params: { kind: "equal_weight" } },
        },
      ],
      edges: [],
    };
    const out = serializeStrategy(strat, "demo");
    expect(out.name).toBe("demo");
    expect(out.config_yaml).toContain("strategy:");
    expect(out.config_yaml).toContain("signals:");
    expect(out.config_yaml).toContain("sizing:");
    expect(out.config_yaml).toContain("fast: 10");
  });
});
