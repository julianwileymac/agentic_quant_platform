/**
 * Domain-specific serializers that transform the canvas {@link FlowGraph}
 * into the payload the FastAPI backend expects.
 *
 * - Agent crew → `POST /agents/crew/run` (CrewAI-style config + prompt)
 * - Data pipeline → `POST /data/ingest` (yfinance-shaped per source node)
 * - Strategy composer → `POST /strategies/` (YAML config + name)
 */
import type { FlowGraph } from "./types";

export interface AgentCrewPayload {
  prompt: string;
  config: {
    nodes: Array<{ id: string; kind: string; label?: string; params?: Record<string, unknown> }>;
    edges: Array<{ source: string; target: string }>;
  };
}

export function serializeAgentCrew(graph: FlowGraph, prompt: string): AgentCrewPayload {
  return {
    prompt,
    config: {
      nodes: graph.nodes.map((n) => ({
        id: n.id,
        kind: n.data.kind,
        label: n.data.label,
        params: n.data.params,
      })),
      edges: graph.edges.map((e) => ({ source: e.source, target: e.target })),
    },
  };
}

export interface DataPipelinePayload {
  jobs: Array<{
    id: string;
    kind: string;
    params: Record<string, unknown>;
    dependencies: string[];
  }>;
}

export function serializeDataPipeline(graph: FlowGraph): DataPipelinePayload {
  const dependencies = new Map<string, string[]>();
  for (const e of graph.edges) {
    const list = dependencies.get(e.target) ?? [];
    list.push(e.source);
    dependencies.set(e.target, list);
  }
  return {
    jobs: graph.nodes.map((n) => ({
      id: n.id,
      kind: n.data.kind,
      params: n.data.params ?? {},
      dependencies: dependencies.get(n.id) ?? [],
    })),
  };
}

export function serializeStrategy(graph: FlowGraph, name: string): {
  name: string;
  config_yaml: string;
} {
  /**
   * Produce a YAML block compatible with `aqp.api.routes.strategies` —
   * essentially a Strategy spec with stages collected from node kinds.
   * The mapping is intentionally straightforward; advanced fields are
   * passed through via each node's `params`.
   */
  const indent = "  ";
  const lines: string[] = [];
  lines.push(`strategy:`);
  lines.push(`${indent}name: ${name}`);

  const grouped: Record<string, FlowGraph["nodes"]> = {};
  for (const n of graph.nodes) {
    const k = n.data.kind.toLowerCase();
    grouped[k] = grouped[k] ?? [];
    grouped[k].push(n);
  }

  function dumpList(key: string, nodes: FlowGraph["nodes"]) {
    if (!nodes.length) return;
    lines.push(`${indent}${key}:`);
    for (const n of nodes) {
      lines.push(`${indent}${indent}- kind: ${n.data.kind}`);
      const params = n.data.params ?? {};
      for (const [pk, pv] of Object.entries(params)) {
        const value = typeof pv === "string" ? `"${pv}"` : Array.isArray(pv) ? `[${pv.join(", ")}]` : String(pv);
        lines.push(`${indent}${indent}${indent}${pk}: ${value}`);
      }
    }
  }

  dumpList("signals", grouped["signal"] ?? []);
  dumpList("factors", grouped["factor"] ?? []);
  dumpList("rules", grouped["rule"] ?? []);
  dumpList("sizing", grouped["sizing"] ?? []);
  dumpList("risk", grouped["risk"] ?? []);
  dumpList("portfolio", grouped["portfolio"] ?? []);
  dumpList("execution", grouped["execution"] ?? []);
  return { name, config_yaml: lines.join("\n") + "\n" };
}
