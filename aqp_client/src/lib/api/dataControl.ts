import { apiFetch } from "./client";

export interface DataControlSummary {
  counts: Record<string, number>;
  recent_runs: Array<Record<string, unknown>>;
  scheduled_manifests: Array<Record<string, unknown>>;
  metadata_sync: Record<string, unknown>;
}

export interface MetadataSyncRequest {
  targets?: Array<"airbyte" | "dagster" | "dbt">;
  enrich_with_llm?: boolean;
  discover_airbyte_schemas?: boolean;
}

export interface TaskAccepted {
  task_id: string;
  stream_url: string;
}

export interface PipelineConfig {
  id: string;
  name: string;
  dataset_catalog_id?: string | null;
  manifest_id?: string | null;
  version: number;
  status: string;
  config_json: Record<string, unknown>;
  sinks: string[];
  automations: Array<Record<string, unknown>>;
  tags: string[];
  notes?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MonitoringRun {
  task_id: string;
  name: string;
  state: string;
  position: "active" | "reserved" | "scheduled";
  worker: string;
  queue?: string | null;
  args?: string | null;
  kwargs?: string | null;
  eta?: string | null;
  time_start?: number | null;
  retries?: number | null;
}

export interface MonitoringRunsResponse {
  generated_at: string;
  workers_seen: number;
  active: MonitoringRun[];
  reserved: MonitoringRun[];
  scheduled: MonitoringRun[];
  totals: Record<string, number>;
  errors: string[];
}

export const dataControlApi = {
  summary: () => apiFetch<DataControlSummary>("/data-control/summary"),

  syncMetadata: (payload: MetadataSyncRequest = {}) =>
    apiFetch<TaskAccepted>("/data-control/metadata/sync", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listPipelineConfigs: (activeOnly = true) =>
    apiFetch<PipelineConfig[]>("/data-control/pipeline-configs", {
      query: { active_only: activeOnly },
    }),

  runManifestBackground: (manifestId: string, triggeredBy = "ui") =>
    apiFetch<TaskAccepted>(
      `/engine/manifests/${encodeURIComponent(manifestId)}/run-background`,
      { method: "POST", query: { triggered_by: triggeredBy } },
    ),

  listMonitoringRuns: () => apiFetch<MonitoringRunsResponse>("/monitoring/runs"),
};
