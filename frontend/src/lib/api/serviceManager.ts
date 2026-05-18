import { apiFetch } from "./client";

export type ServiceName =
  | "trino"
  | "polaris"
  | "iceberg"
  | "superset"
  | "airbyte"
  | "dagster"
  | "neo4j";

export interface ServiceHealth {
  ok: boolean;
  service?: string;
  error?: string | null;
  [key: string]: unknown;
}

export interface ServiceManagerHealth {
  ok: boolean;
  services: Record<ServiceName, ServiceHealth>;
  config: Record<string, unknown>;
}

export interface IcebergBootstrapStep {
  name: string;
  status: string;
  detail?: string;
  payload?: Record<string, unknown>;
}

export interface IcebergBootstrapReport {
  catalog: string;
  principal: string;
  principal_role: string;
  catalog_role: string;
  privilege: string;
  duration_seconds: number;
  success: boolean;
  bootstrap_required: boolean;
  steps: IcebergBootstrapStep[];
  credentials_file?: string | null;
  credentials_persisted: boolean;
  last_error?: string | null;
}

export interface IcebergStatus {
  catalog: string;
  principal: string;
  principal_role: string;
  catalog_role: string;
  privilege: string;
  polaris_reachable: boolean;
  catalog_present: boolean;
  principal_present: boolean;
  principal_role_present: boolean;
  catalog_role_present: boolean;
  credentials_persisted: boolean;
  credentials_file?: string;
  error?: string | null;
}

export interface TrinoVerification {
  coordinator_ok: boolean;
  coordinator_url: string;
  node_id?: string | null;
  node_version?: string | null;
  query_ok: boolean;
  iceberg_catalog_ok: boolean;
  catalogs?: string[];
  iceberg_schemas?: string[];
  error?: string | null;
}

export interface TrinoQueryRow {
  query_id: string;
  state: string;
  user?: string | null;
  source?: string | null;
  catalog?: string | null;
  schema?: string | null;
  elapsed_seconds?: number | null;
  queued_seconds?: number | null;
  error?: string | null;
  statement?: string;
  created?: string | null;
}

export const serviceManagerApi = {
  health: () => apiFetch<ServiceManagerHealth>("/service-manager/health"),
  logs: (name: ServiceName, lines = 200) =>
    apiFetch<{ ok: boolean; stdout?: string; stderr?: string; error?: string }>(
      `/service-manager/${name}/logs`,
      { query: { lines } },
    ),
  action: (name: ServiceName, action: "start" | "stop" | "restart") =>
    apiFetch<Record<string, unknown>>(`/service-manager/${name}/actions`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  icebergStatus: () => apiFetch<IcebergStatus>("/service-manager/iceberg/status"),
  icebergBootstrap: () =>
    apiFetch<IcebergBootstrapReport>("/service-manager/iceberg/bootstrap", { method: "POST" }),
  trinoVerify: () => apiFetch<TrinoVerification>("/service-manager/trino/verify", { method: "POST" }),
  trinoQueries: (limit = 50) =>
    apiFetch<{ queries: TrinoQueryRow[]; count: number }>("/service-manager/trino/queries", {
      query: { limit },
    }),
};
