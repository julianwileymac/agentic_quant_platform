import { apiFetch } from "./client";

export interface EntitySummary {
  id: string;
  kind: string;
  canonical_name: string;
  short_name?: string | null;
  primary_identifier?: string | null;
  primary_identifier_scheme?: string | null;
  description?: string | null;
  tags?: string[];
  confidence?: number | null;
  source_dataset?: string | null;
  source_extractor?: string | null;
  is_canonical?: boolean;
  instrument_id?: string | null;
  issuer_id?: string | null;
  parent_id?: string | null;
  attributes?: Record<string, unknown>;
}

export interface EntityIdentifier {
  id: string;
  scheme: string;
  value: string;
  source?: string | null;
  confidence?: number | null;
}

export interface EntityAnnotation {
  id: string;
  kind: string;
  content: string;
  author?: string | null;
  model?: string | null;
  provider?: string | null;
  citations?: string[];
  confidence?: number | null;
  created_at: string;
}

export interface EntityDetail extends EntitySummary {
  identifiers?: EntityIdentifier[];
  annotations?: EntityAnnotation[];
}

export interface EntityRelation {
  id: string;
  subject_id: string;
  predicate: string;
  object_id: string;
  confidence?: number | null;
  provenance?: string | null;
  properties?: Record<string, unknown>;
}

export interface EntityGraphNode {
  id: string;
  label: string;
  kind: string;
  meta?: Record<string, unknown>;
}

export interface EntityGraphEdge {
  from_id: string;
  to_id: string;
  relationship_type: string;
  meta?: Record<string, unknown>;
}

export interface EntityGraphPayload {
  root_id?: string | null;
  depth: number;
  nodes: EntityGraphNode[];
  edges: EntityGraphEdge[];
  error?: string;
}

export interface ActiveInstrumentPayload {
  id: string;
  vt_symbol: string;
  ticker: string;
  exchange?: string | null;
  asset_class?: string | null;
  security_type?: string | null;
  sector?: string | null;
  industry?: string | null;
}

export const entityRegistryApi = {
  list: (params?: { kind?: string; source_dataset?: string; canonical_only?: boolean; limit?: number; offset?: number }) =>
    apiFetch<EntitySummary[]>("/registry/entities", params ? { query: params } : {}),

  search: (q: string, kind?: string, limit?: number) =>
    apiFetch<EntitySummary[]>("/registry/entities/search", {
      query: { q, ...(kind ? { kind } : {}), ...(limit ? { limit } : {}) },
    }),

  get: (id: string) =>
    apiFetch<EntityDetail>(`/registry/entities/${encodeURIComponent(id)}`),

  neighbors: (id: string, depth = 1, limit = 64) =>
    apiFetch<{ entity_id: string; outgoing: EntityRelation[]; incoming: EntityRelation[] }>(
      `/registry/entities/${encodeURIComponent(id)}/neighbors`,
      { query: { depth, limit } },
    ),

  graph: (params?: { root_id?: string; q?: string; depth?: number; limit?: number }) =>
    apiFetch<EntityGraphPayload>("/registry/entities/graph/explorer", params ? { query: params } : {}),

  activeInstruments: (params?: { refresh?: boolean; limit?: number }) =>
    apiFetch<{ count: number; instruments: ActiveInstrumentPayload[] }>(
      "/registry/entities/instruments/active",
      params ? { query: params } : {},
    ),

  syncInstruments: (limit = 5000) =>
    apiFetch<{ seen: number; upserted: number }>("/registry/entities/instruments/sync", {
      method: "POST",
      query: { limit },
    }),

  instrumentLoadTemplate: (payload: {
    vt_symbols: string[];
    provider?: string;
    start?: string;
    end?: string;
    interval?: string;
    dataset_template?: string;
    dry_run?: boolean;
  }) =>
    apiFetch<Record<string, unknown>>("/registry/entities/instruments/load-template", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  datasets: (id: string) =>
    apiFetch<{ entity_id: string; datasets: Array<Record<string, unknown>> }>(
      `/registry/entities/${encodeURIComponent(id)}/datasets`,
    ),

  create: (payload: Partial<EntitySummary> & { canonical_name: string; kind: string }) =>
    apiFetch<EntitySummary>("/registry/entities", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  addIdentifier: (
    id: string,
    payload: { scheme: string; value: string; source?: string; confidence?: number },
  ) =>
    apiFetch<EntityIdentifier>(
      `/registry/entities/${encodeURIComponent(id)}/identifiers`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  addAnnotation: (
    id: string,
    payload: {
      content: string;
      kind?: string;
      author?: string;
      citations?: string[];
      confidence?: number;
    },
  ) =>
    apiFetch<EntityAnnotation>(
      `/registry/entities/${encodeURIComponent(id)}/annotations`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  triggerExtract: (payload: {
    flavor: string;
    iceberg_identifier?: string;
    head_rows?: number;
    extractor_kwargs?: Record<string, unknown>;
  }) =>
    apiFetch<{ task_id: string; status: string }>("/registry/entities/extract", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  triggerEnrich: (payload: {
    enricher: string;
    entity_ids: string[];
    enricher_kwargs?: Record<string, unknown>;
  }) =>
    apiFetch<{ task_ids: string[]; status: string; count: number }>(
      "/registry/entities/enrich",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  listExtractorKinds: () =>
    apiFetch<{ extractors: Array<{ name: string; class_name: string }> }>(
      "/registry/entities/_meta/extractors",
    ),

  listEnricherKinds: () =>
    apiFetch<{ enrichers: Array<{ name: string; class_name: string }> }>(
      "/registry/entities/_meta/enrichers",
    ),
};
