import type { FlowGraph } from "@/components/flow/types";

export interface StrategySpec {
  name: string;
  signals: Record<string, unknown>[];
  factors: Record<string, unknown>[];
  rules: Record<string, unknown>[];
  sizing: Record<string, unknown>[];
  risk: Record<string, unknown>[];
  portfolio: Record<string, unknown> | null;
  execution: Record<string, unknown> | null;
  wiring: Array<{ source: string; target: string }>;
}

export function serializeStrategySpec(graph: FlowGraph, name: string): StrategySpec {
  const spec: StrategySpec = {
    name,
    signals: [],
    factors: [],
    rules: [],
    sizing: [],
    risk: [],
    portfolio: null,
    execution: null,
    wiring: graph.edges.map((e) => ({ source: e.source, target: e.target })),
  };
  for (const node of graph.nodes) {
    const params = node.data.params ?? {};
    const labelled = { id: node.id, label: node.data.label ?? node.data.kind, ...params };
    switch (node.data.kind) {
      case "Signal":
        spec.signals.push(labelled);
        break;
      case "Factor":
        spec.factors.push(labelled);
        break;
      case "Rule":
        spec.rules.push(labelled);
        break;
      case "Sizing":
        spec.sizing.push(labelled);
        break;
      case "Risk":
        spec.risk.push(labelled);
        break;
      case "Portfolio":
        spec.portfolio = labelled;
        break;
      case "Execution":
        spec.execution = labelled;
        break;
      default:
        break;
    }
  }
  return spec;
}
