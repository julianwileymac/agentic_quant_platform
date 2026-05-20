import { apiFetch } from "./client";

// TODO(openapi): regenerate via make webui-gen-api once /metadata/aspects/* routes are pushed.

export type LineageDirection = "upstream" | "downstream" | "both";

export interface MetadataEntitySummary {
  urn: string;
  entity_type: string;
  created_at: string;
  updated_at: string;
  aspect_count: number;
}

export interface MetadataEntityAspectLatest {
  id: string;
  version: number;
  payload: Record<string, unknown>;
  payload_hash: string;
  created_at: string;
  created_by: string | null;
  system_metadata: Record<string, unknown>;
}

export interface MetadataEntityDetail {
  urn: string;
  entity_type: string;
  created_at: string;
  updated_at: string;
  aspects: Record<string, MetadataEntityAspectLatest>;
}

export interface EntityAspectRow {
  id: string;
  aspect_name: string;
  version: number;
  payload: Record<string, unknown>;
  payload_hash: string;
  created_at: string;
  created_by: string | null;
  system_metadata: Record<string, unknown>;
}

export interface LineageEdgeWire {
  from_entity: string;
  to_entity: string;
  edge_type: string;
  metadata: Record<string, unknown>;
}

export interface EntityLineagePayload {
  entity: string;
  upstream_edges: LineageEdgeWire[];
  downstream_edges: LineageEdgeWire[];
  depth: number;
}

export interface MetadataAspectStats {
  entity_count_by_type: Record<string, number>;
  aspect_count_by_name: Record<string, number>;
  recent_writes: Array<{
    urn: string;
    aspect_name: string;
    version: number;
    created_at: string;
  }>;
}

export interface ListMetadataEntitiesParams {
  entity_type?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface MetadataEntityHistoryParams {
  aspect_name?: string;
  limit?: number;
}

export interface MetadataLineageParams {
  depth?: number;
  direction?: LineageDirection;
}

interface MetadataEntityListResponse {
  items: MetadataEntitySummary[];
  total: number;
}

export async function listMetadataEntities(
  params: ListMetadataEntitiesParams = {},
): Promise<MetadataEntitySummary[]> {
  const response = await apiFetch<MetadataEntityListResponse>(
    "/metadata/aspects/entities",
    {
      query: {
        entity_type: params.entity_type,
        search: params.search,
        limit: params.limit,
        offset: params.offset,
      },
    },
  );
  return response.items;
}

export async function listMetadataEntitiesPage(
  params: ListMetadataEntitiesParams = {},
): Promise<MetadataEntityListResponse> {
  return apiFetch<MetadataEntityListResponse>("/metadata/aspects/entities", {
    query: {
      entity_type: params.entity_type,
      search: params.search,
      limit: params.limit,
      offset: params.offset,
    },
  });
}

export async function describeMetadataEntity(
  urn: string,
): Promise<MetadataEntityDetail> {
  return apiFetch<MetadataEntityDetail>(
    `/metadata/aspects/entities/${encodeURIComponent(urn)}`,
  );
}

export async function metadataEntityHistory(
  urn: string,
  params: MetadataEntityHistoryParams = {},
): Promise<EntityAspectRow[]> {
  return apiFetch<EntityAspectRow[]>(
    `/metadata/aspects/entities/${encodeURIComponent(urn)}/history`,
    {
      query: {
        aspect_name: params.aspect_name,
        limit: params.limit,
      },
    },
  );
}

export async function metadataLineage(
  urn: string,
  params: MetadataLineageParams = {},
): Promise<EntityLineagePayload> {
  return apiFetch<EntityLineagePayload>(
    `/metadata/aspects/lineage/${encodeURIComponent(urn)}`,
    {
      query: {
        depth: params.depth,
        direction: params.direction,
      },
    },
  );
}

export async function metadataAspectStats(): Promise<MetadataAspectStats> {
  return apiFetch<MetadataAspectStats>("/metadata/aspects/stats");
}
