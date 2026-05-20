import type { FlowGraph } from "@/components/flow/types";

export interface SerializedDatasetRef {
  iceberg_identifier?: string;
  dataset_version_id?: string;
  dataset_cfg?: Record<string, unknown>;
  filters?: Record<string, unknown>;
  columns?: string[];
  start?: string;
  end?: string;
  limit?: number;
}

export interface SerializedAnalysisStep {
  alias: string;
  flow_ref: {
    flow: string;
    params: Record<string, unknown>;
    inputs?: Record<string, string>;
  };
  persist?: boolean;
  notes?: string;
}

export interface SerializedAnalysisSpec {
  name: string;
  slug?: string | undefined;
  kind?: string | undefined;
  description?: string | undefined;
  dataset: SerializedDatasetRef;
  steps: SerializedAnalysisStep[];
  business_metadata?:
    | {
        data_owner: string;
        semantic_definition: string;
        domain?: string | undefined;
        sla_class?: string | undefined;
        reliability_score?: number | undefined;
      }
    | undefined;
}

export interface SerializeMeta {
  name: string;
  description?: string | undefined;
  dataset: SerializedDatasetRef;
  data_owner: string;
  semantic_definition: string;
  domain?: string | undefined;
}

/**
 * Translate the Composer's xyflow graph into an :class:`AnalysisSpec`
 * payload suitable for ``POST /analysis/specs``.
 *
 * Each node's ``kind`` IS the namespaced flow name (set by the
 * palette), so serialisation is a simple map. Aliases default to the
 * node id when the user hasn't named the node.
 */
export function serializeAnalysisSpec(
  graph: FlowGraph,
  meta: SerializeMeta,
): SerializedAnalysisSpec {
  const steps: SerializedAnalysisStep[] = graph.nodes
    .filter((node) => Boolean(node.data?.kind))
    .map((node) => ({
      alias: aliasFor(node),
      flow_ref: {
        flow: node.data.kind,
        params: { ...(node.data.params ?? {}) },
      },
      persist: true,
      ...(node.data.notes ? { notes: node.data.notes } : {}),
    }));

  const out: SerializedAnalysisSpec = {
    name: meta.name,
    ...(meta.description ? { description: meta.description } : {}),
    dataset: meta.dataset,
    steps,
    business_metadata: {
      data_owner: meta.data_owner,
      semantic_definition: meta.semantic_definition,
      ...(meta.domain ? { domain: meta.domain } : {}),
    },
  };
  return out;
}

function aliasFor(node: FlowGraph["nodes"][number]): string {
  const candidate =
    typeof node.data?.label === "string" && node.data.label.trim()
      ? node.data.label.trim()
      : node.id;
  return candidate.replace(/[^A-Za-z0-9_:.\-]+/g, "_").slice(0, 60);
}
