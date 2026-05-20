import type { FlowGraph } from "@/components/flow/types";

export interface DataPipelineSpec {
  name: string;
  sources: Record<string, unknown>[];
  transforms: Record<string, unknown>[];
  features: Record<string, unknown>[];
  sinks: Record<string, unknown>[];
  plan: Record<string, unknown> | null;
  load: Record<string, unknown> | null;
  dbt: Record<string, unknown> | null;
  templates: Record<string, unknown>[];
  wiring: Array<{ source: string; target: string }>;
}

export function serializeDataPipelineSpec(graph: FlowGraph, name: string): DataPipelineSpec {
  const spec: DataPipelineSpec = {
    name,
    sources: [],
    transforms: [],
    features: [],
    sinks: [],
    plan: null,
    load: null,
    dbt: null,
    templates: [],
    wiring: graph.edges.map((e) => ({ source: e.source, target: e.target })),
  };
  for (const node of graph.nodes) {
    const params = node.data.params ?? {};
    const labelled = { id: node.id, label: node.data.label ?? node.data.kind, ...params };
    switch (node.data.kind) {
      case "Source":
        spec.sources.push(labelled);
        break;
      case "Template":
        spec.templates.push(labelled);
        break;
      case "Transform":
        spec.transforms.push(labelled);
        break;
      case "Feature":
        spec.features.push(labelled);
        break;
      case "Iceberg":
      case "Parquet":
      case "Index":
        spec.sinks.push({ ...labelled, sink_kind: node.data.kind.toLowerCase() });
        break;
      case "Plan":
        spec.plan = labelled;
        break;
      case "Load":
        spec.load = labelled;
        break;
      case "Dbt":
        spec.dbt = labelled;
        break;
      default:
        break;
    }
  }
  return spec;
}
