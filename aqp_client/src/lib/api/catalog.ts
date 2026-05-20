import { apiFetch } from "./client";

export interface CatalogNamespace {
  namespace: string;
  table_count?: number;
  medallion_layer?: "bronze" | "silver" | "gold" | string;
  description?: string;
}

export interface CatalogDatasetVersion {
  id: string;
  catalog_id: string;
  version: number;
  status: string;
  dataset_hash?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  row_count: number;
  symbol_count: number;
  created_at?: string | null;
}

export interface CatalogTableSummary {
  namespace: string;
  name: string;
  row_count?: number | null;
  partition_spec?: string[];
  last_snapshot_at?: string | null;
  medallion_layer?: string;
  business_metadata?: Record<string, unknown>;
  data_contract?: Record<string, unknown>;
  dataset_id?: string | null;
  description?: string | null;
  tags?: string[];
  dataset_created_at?: string | null;
  dataset_updated_at?: string | null;
}

export interface CatalogColumn {
  name: string;
  type: string;
  nullable?: boolean;
  doc?: string | null;
}

export interface CatalogTableDetail extends CatalogTableSummary {
  schema?: { fields: CatalogColumn[] };
  partition_spec_full?: Array<{ source_id?: number; transform?: string; field?: string }>;
  business_metadata?: Record<string, unknown>;
  data_contract?: Record<string, unknown>;
  location?: string | null;
  current_snapshot_id?: string | number | null;
  dataset_versions?: CatalogDatasetVersion[];
}

export interface CatalogSnapshot {
  snapshot_id: string;
  parent_snapshot_id?: string | null;
  sequence_number?: number;
  timestamp?: string;
  manifest_list?: string;
  summary?: Record<string, unknown>;
}

export interface DuckQueryResult {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  duration_ms?: number;
  truncated?: boolean;
}

export interface MetadataDataset {
  id: string;
  name: string;
  provider: string;
  domain: string;
  namespace?: string | null;
  table?: string | null;
  iceberg_identifier?: string | null;
  storage_uri?: string | null;
  source_uri?: string | null;
  frequency?: string | null;
  load_mode: string;
  description?: string | null;
  tags: string[];
  latest_version?: number | null;
  latest_row_count?: number | null;
  latest_symbol_count?: number | null;
  latest_file_count?: number | null;
  medallion_layer?: string | null;
  business_metadata?: Record<string, unknown>;
  data_contract?: Record<string, unknown>;
  updated_at?: string | null;
  created_at?: string | null;
}

export interface MetadataLineage {
  dataset: Record<string, unknown> | null;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

function path(suffix: string): string {
  return `/data/catalog${suffix}`;
}

export const catalogApi = {
  namespaces(): Promise<CatalogNamespace[]> {
    return apiFetch<CatalogNamespace[]>(path("/namespaces"));
  },
  tables(namespace: string): Promise<CatalogTableSummary[]> {
    return apiFetch<CatalogTableSummary[]>(path(`/${encodeURIComponent(namespace)}`));
  },
  tableDetail(namespace: string, name: string): Promise<CatalogTableDetail> {
    return apiFetch<CatalogTableDetail>(
      path(`/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`),
    );
  },
  snapshots(namespace: string, name: string): Promise<CatalogSnapshot[]> {
    return apiFetch<CatalogSnapshot[]>(
      path(`/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/snapshots`),
    );
  },
  sample(namespace: string, name: string, limit = 100): Promise<DuckQueryResult> {
    return apiFetch<DuckQueryResult>(
      path(`/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/sample`),
      { query: { limit } },
    );
  },
  runDuckQuery(sql: string): Promise<DuckQueryResult> {
    return apiFetch<DuckQueryResult>("/data/duckdb/query", {
      method: "POST",
      body: JSON.stringify({ sql }),
    });
  },
  runTableQuery(namespace: string, name: string, sql: string, limit = 500): Promise<DuckQueryResult> {
    return apiFetch<DuckQueryResult>(
      path(`/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/query`),
      { method: "POST", body: JSON.stringify({ sql, limit }) },
    );
  },
  metadataDataset(id: string): Promise<MetadataDataset> {
    return apiFetch<MetadataDataset>(`/metadata/catalog/datasets/${encodeURIComponent(id)}`);
  },
  createMetadataDataset(payload: Partial<MetadataDataset> & { name: string }): Promise<MetadataDataset> {
    return apiFetch<MetadataDataset>("/metadata/catalog/datasets", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  patchMetadataDataset(id: string, payload: Partial<MetadataDataset>): Promise<MetadataDataset> {
    return apiFetch<MetadataDataset>(`/metadata/catalog/datasets/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  datasetLineage(id: string): Promise<MetadataLineage> {
    return apiFetch<MetadataLineage>(`/metadata/catalog/datasets/${encodeURIComponent(id)}/lineage`);
  },
  createDatasetFromSource(
    source: string,
    payload: {
      name: string;
      namespace: string;
      table: string;
      description?: string | null;
      domain?: string;
      medallion_layer?: string | null;
      tags?: string[];
      source_node?: string | null;
      source_kwargs?: Record<string, unknown>;
      transforms?: Array<Record<string, unknown>>;
      schedule_cron?: string | null;
      run_now?: boolean;
    },
  ): Promise<{ dataset_id: string; manifest_id: string; iceberg_identifier: string; run_id?: string | null; status: string }> {
    return apiFetch(`/sources/${encodeURIComponent(source)}/datasets`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
