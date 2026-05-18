import { apiFetch } from "./client";

export interface KgNode {
  id: string;
  label: string;
  kind: string;
  properties?: Record<string, unknown>;
  /** Optional 2D coords if the backend pre-laid out the graph. */
  x?: number;
  y?: number;
}

export interface KgEdge {
  id: string;
  source: string;
  target: string;
  kind?: string;
  weight?: number;
  label?: string;
}

export interface KgGraph {
  nodes: KgNode[];
  edges: KgEdge[];
}

export interface KgSearchHit {
  id: string;
  label: string;
  kind: string;
  score: number;
  snippet?: string;
}

export const kgApi = {
  graph: (params?: { entity_kind?: string; limit?: number }): Promise<KgGraph> =>
    apiFetch<KgGraph>("/data/kg/graph", params ? { query: params } : {}),
  entityGraph: (params?: { limit?: number }): Promise<KgGraph> =>
    apiFetch<KgGraph>("/data/entity-graph", params ? { query: params } : {}),
  search: (query: string, limit = 50): Promise<KgSearchHit[]> =>
    apiFetch<KgSearchHit[]>("/data/kg/search", { query: { q: query, limit } }),
  node: (id: string): Promise<{ node: KgNode; neighbours: KgNode[]; edges: KgEdge[] }> =>
    apiFetch(`/data/kg/${encodeURIComponent(id)}`),
};
