import { apiFetch } from "./client";

export interface AirbyteConnector {
  id: string;
  name: string;
  kind: "source" | "destination";
  runtime: "full_airbyte" | "embedded" | "hybrid";
  description: string;
  service?: string | null;
  tags: string[];
  capabilities: string[];
  streams: Array<{ name: string; entity_kind?: string | null }>;
}

export interface AirbyteConnection {
  id: string;
  name: string;
  source_connector_id: string;
  destination_connector_id: string;
  namespace: string;
  airbyte_connection_id?: string | null;
  enabled: boolean;
  last_sync_status?: string | null;
}

export interface AirbyteRun {
  id: string;
  connection_id?: string | null;
  task_id?: string | null;
  airbyte_job_id?: string | null;
  runtime: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  error?: string | null;
}

export interface TaskAccepted {
  task_id: string;
  stream_url: string;
}

export const AirbyteApi = {
  health: () => apiFetch<Record<string, unknown>>("/airbyte/health"),
  summary: () => apiFetch<Record<string, unknown>>("/airbyte/connectors/summary"),
  connectors: (kind?: "source" | "destination") =>
    apiFetch<AirbyteConnector[]>("/airbyte/connectors", kind ? { query: { kind } } : {}),
  connections: () => apiFetch<AirbyteConnection[]>("/airbyte/connections"),
  runs: () => apiFetch<AirbyteRun[]>("/airbyte/runs"),
  remoteMetadata: () => apiFetch<Record<string, unknown>>("/airbyte/metadata/remote"),
  syncMetadata: (discoverSchemas = true, enrichWithLlm = false) =>
    apiFetch<TaskAccepted>("/airbyte/metadata/sync", {
      method: "POST",
      body: JSON.stringify({ discover_schemas: discoverSchemas, enrich_with_llm: enrichWithLlm }),
    }),
  discover: (connector_id: string, config: Record<string, unknown> = {}) =>
    apiFetch<TaskAccepted>("/airbyte/discover", {
      method: "POST",
      body: JSON.stringify({ connector_id, config, runtime: "embedded" }),
    }),
  embeddedRead: (connector_id: string, config: Record<string, unknown> = {}) =>
    apiFetch<TaskAccepted>("/airbyte/embedded/read", {
      method: "POST",
      body: JSON.stringify({ connector_id, config, dry_run: true, limit: 100 }),
    }),
  sync: (connection_id: string) =>
    apiFetch<TaskAccepted>("/airbyte/sync", {
      method: "POST",
      body: JSON.stringify({ connection_id, wait: false, materialize_after_sync: false }),
    }),
};
