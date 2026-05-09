import type { FlowGraph } from "@/components/flow/types";

export interface CrewSpec {
  name: string;
  llm: Record<string, unknown> | null;
  memory: Record<string, unknown> | null;
  tools: Record<string, unknown>[];
  agents: Record<string, unknown>[];
  tasks: Record<string, unknown>[];
  outputs: Record<string, unknown>[];
  wiring: Array<{ source: string; target: string }>;
}

export function serializeCrewSpec(graph: FlowGraph, name: string): CrewSpec {
  const spec: CrewSpec = {
    name,
    llm: null,
    memory: null,
    tools: [],
    agents: [],
    tasks: [],
    outputs: [],
    wiring: graph.edges.map((e) => ({ source: e.source, target: e.target })),
  };
  for (const node of graph.nodes) {
    const params = node.data.params ?? {};
    const labelled = { id: node.id, label: node.data.label ?? node.data.kind, ...params };
    switch (node.data.kind) {
      case "LLM":
        spec.llm = labelled;
        break;
      case "Memory":
        spec.memory = labelled;
        break;
      case "Tool":
        spec.tools.push(labelled);
        break;
      case "Agent":
        spec.agents.push(labelled);
        break;
      case "Task":
        spec.tasks.push(labelled);
        break;
      case "Output":
        spec.outputs.push(labelled);
        break;
      default:
        break;
    }
  }
  return spec;
}
