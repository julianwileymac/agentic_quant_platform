/**
 * Serializer that turns a node-and-wire :class:`FlowGraph` (built with
 * the Bot Builder) into a server-side ``BotSpec`` payload.
 *
 * The flow graph carries one node per spec slot:
 *
 * - ``Universe`` -> ``spec.universe``
 * - ``DataPipeline`` -> ``spec.data_pipeline``
 * - ``Strategy`` -> ``spec.strategy``
 * - ``Engine`` -> ``spec.backtest``
 * - ``MLModel`` -> ``spec.ml_models[]``
 * - ``Agent`` -> ``spec.agents[]``
 * - ``RAG`` -> ``spec.rag[]``
 * - ``Metric`` -> ``spec.metrics[]``
 * - ``Risk`` -> ``spec.risk``
 * - ``Deploy`` -> ``spec.deployment``
 *
 * Edges are informational on the canvas (visual flow) and are not
 * required to derive the spec — order is taken from the node array,
 * which the FlowCanvas keeps stable across renders.
 */

import type { BotKind } from "@/lib/api/bots";
import type { FlowGraph } from "@/components/flow/types";

export interface BotSpecMeta {
  name: string;
  slug?: string;
  kind: BotKind;
  description?: string;
}

export function serializeBotSpec(graph: FlowGraph, meta: BotSpecMeta): Record<string, unknown> {
  const spec: Record<string, unknown> = {
    name: meta.name,
    slug: meta.slug ?? slugify(meta.name),
    kind: meta.kind,
    description: meta.description ?? "",
    universe: { symbols: [] as string[] },
    data_pipeline: null as Record<string, unknown> | null,
    strategy: null as Record<string, unknown> | null,
    backtest: null as Record<string, unknown> | null,
    ml_models: [] as Record<string, unknown>[],
    agents: [] as Record<string, unknown>[],
    rag: [] as Record<string, unknown>[],
    metrics: [] as Record<string, unknown>[],
    risk: {} as Record<string, unknown>,
    deployment: { target: "paper_session" } as Record<string, unknown>,
  };

  for (const node of graph.nodes) {
    const params = node.data.params ?? {};
    switch (node.data.kind) {
      case "Universe": {
        const symbols = Array.isArray(params.symbols) ? params.symbols : [];
        const model = params.class
          ? { class: params.class, module_path: params.module_path, kwargs: params.kwargs ?? {} }
          : undefined;
        spec.universe = { symbols, model: model ?? null };
        break;
      }
      case "DataPipeline":
        spec.data_pipeline = { ...params };
        break;
      case "Strategy":
        spec.strategy = { ...params };
        break;
      case "Engine":
        spec.backtest = { ...params };
        break;
      case "MLModel":
        if (params.deployment_id) {
          (spec.ml_models as Record<string, unknown>[]).push({
            deployment_id: params.deployment_id,
            role: params.role ?? "alpha",
            weight: params.weight ?? 1.0,
          });
        }
        break;
      case "Agent":
        if (params.spec_name) {
          (spec.agents as Record<string, unknown>[]).push({
            spec_name: params.spec_name,
            role: params.role ?? "advisor",
            inputs_template: params.inputs_template ?? {},
            enabled: params.enabled !== false,
          });
        }
        break;
      case "RAG":
        (spec.rag as Record<string, unknown>[]).push({
          levels: params.levels ?? ["l3"],
          orders: params.orders ?? ["first", "second", "third"],
          corpora: params.corpora ?? [],
          per_level_k: params.per_level_k ?? 5,
          final_k: params.final_k ?? 8,
          rerank: params.rerank ?? true,
          compress: params.compress ?? true,
        });
        break;
      case "Metric":
        (spec.metrics as Record<string, unknown>[]).push({
          name: params.name,
          threshold: params.threshold ?? null,
          direction: params.direction ?? "max",
        });
        break;
      case "Risk":
        spec.risk = { ...params };
        break;
      case "Deploy":
        spec.deployment = { ...params };
        break;
      default:
        // Unknown nodes are ignored — the canvas may drop annotation /
        // sticky-note nodes here in the future.
        break;
    }
  }

  return spec;
}

/**
 * Inverse: build a starter graph from an existing ``BotSpec`` so the
 * builder can edit a saved bot. Each non-empty slot becomes one node.
 */
export function deserializeBotSpec(spec: Record<string, unknown>): FlowGraph {
  const nodes: FlowGraph["nodes"] = [];
  const edges: FlowGraph["edges"] = [];
  let y = 60;
  let xRow = 60;
  let lastId: string | null = null;

  function pushNode(id: string, kind: string, label: string, params: Record<string, unknown>): void {
    nodes.push({
      id,
      type: "aqp",
      position: { x: xRow, y },
      data: { kind, label, params },
    });
    if (lastId) {
      edges.push({ id: `e-${lastId}-${id}`, source: lastId, target: id });
    }
    lastId = id;
    xRow += 280;
    if (xRow > 1400) {
      xRow = 60;
      y += 140;
    }
  }

  const universe = (spec.universe ?? {}) as Record<string, unknown>;
  const symbols = (universe.symbols as unknown[]) ?? [];
  if (symbols.length || universe.model) {
    pushNode("uni-1", "Universe", `Universe (${symbols.length} symbols)`, universe);
  }

  if (spec.data_pipeline) {
    pushNode("data-1", "DataPipeline", "Data pipeline", spec.data_pipeline as Record<string, unknown>);
  }
  if (spec.strategy) {
    const cls = (spec.strategy as Record<string, unknown>).class as string | undefined;
    pushNode("strat-1", "Strategy", cls ?? "Strategy", spec.strategy as Record<string, unknown>);
  }
  if (spec.backtest) {
    const eng = (spec.backtest as Record<string, unknown>).engine as string | undefined;
    pushNode("eng-1", "Engine", `Engine: ${eng ?? "(class)"}`, spec.backtest as Record<string, unknown>);
  }
  ((spec.ml_models as Record<string, unknown>[]) ?? []).forEach((m, i) => {
    pushNode(`ml-${i + 1}`, "MLModel", `ML: ${m.deployment_id}`, m);
  });
  ((spec.agents as Record<string, unknown>[]) ?? []).forEach((a, i) => {
    pushNode(`ag-${i + 1}`, "Agent", `Agent: ${a.spec_name}`, a);
  });
  ((spec.rag as Record<string, unknown>[]) ?? []).forEach((r, i) => {
    const corpora = ((r.corpora as unknown[]) ?? []).join(", ");
    pushNode(`rag-${i + 1}`, "RAG", `RAG: ${corpora || "(walk)"}`, r);
  });
  ((spec.metrics as Record<string, unknown>[]) ?? []).forEach((m, i) => {
    pushNode(`metric-${i + 1}`, "Metric", `Metric: ${m.name}`, m);
  });
  if (spec.risk && Object.keys(spec.risk as Record<string, unknown>).length > 0) {
    pushNode("risk-1", "Risk", "Risk caps", spec.risk as Record<string, unknown>);
  }
  if (spec.deployment) {
    const target = (spec.deployment as Record<string, unknown>).target as string | undefined;
    pushNode("dep-1", "Deploy", `Deploy: ${target ?? "paper_session"}`, spec.deployment as Record<string, unknown>);
  }

  return { domain: "bot", version: 1, nodes, edges };
}

export function slugify(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}
