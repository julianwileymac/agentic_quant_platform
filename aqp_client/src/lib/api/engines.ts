import { apiFetch } from "./client";

export type ComputeBackendKind = "auto" | "local" | "dask" | "ray";

export interface NodeSpec {
  name: string;
  kwargs: Record<string, unknown>;
  label?: string | null;
  enabled?: boolean;
}

export interface ComputeSpec {
  backend: ComputeBackendKind;
  chunk_rows?: number;
  max_concurrent_pipelines?: number;
  dask_address?: string | null;
  ray_address?: string | null;
  n_workers?: number | null;
  threads_per_worker?: number | null;
  extras?: Record<string, unknown>;
}

export interface PartitionSpec {
  kind: "none" | "daily" | "weekly" | "monthly" | "symbol" | "static";
  key?: string | null;
  start?: string | null;
  end?: string | null;
  values?: string[];
}

export interface SchedulingSpec {
  cron?: string | null;
  timezone?: string;
  enabled?: boolean;
}

export interface PipelineManifest {
  id?: string | null;
  name: string;
  namespace: string;
  description?: string | null;
  tags?: string[];
  source: NodeSpec;
  transforms?: NodeSpec[];
  sink: NodeSpec;
  compute?: ComputeSpec;
  partitions?: PartitionSpec;
  schedule?: SchedulingSpec;
  owner?: string | null;
  version?: number;
  enabled?: boolean;
}

export interface ManifestSummary {
  id: string;
  name: string;
  namespace: string;
  description: string | null;
  owner: string | null;
  version: number;
  enabled: boolean;
  tags: string[];
  compute_backend: string | null;
  schedule_cron: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
}

export interface RunSummary {
  id: string;
  manifest_id: string | null;
  namespace: string;
  name: string;
  backend: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  rows_written: number;
  tables_written: number;
  triggered_by: string | null;
  duration_seconds: number | null;
}

export interface ComputeStatusResponse {
  default_backend: ComputeBackendKind;
  thresholds: Record<string, number>;
  dask: {
    available: boolean;
    scheduler_address?: string | null;
    n_workers?: number | null;
    threads_per_worker?: number | null;
  };
  ray: {
    available: boolean;
    address?: string | null;
    init_kwargs?: Record<string, unknown> | null;
  };
  engine: {
    default_chunk_rows: number;
    max_concurrent_pipelines: number;
  };
}

export const enginesApi = {
  computeStatus: () => apiFetch<ComputeStatusResponse>("/compute/status"),
  pickCompute: (payload: { rows?: number; bytes?: number; requested?: ComputeBackendKind }) =>
    apiFetch<ComputeSpec>("/compute/pick", {
      method: "POST",
      body: JSON.stringify({
        rows: payload.rows ?? 0,
        bytes: payload.bytes ?? 0,
        requested: payload.requested ?? "auto",
      }),
    }),

  listManifests: (params?: { namespace?: string; enabled_only?: boolean; limit?: number }) =>
    apiFetch<ManifestSummary[]>("/engine/manifests", params ? { query: params } : {}),

  saveManifest: (spec: PipelineManifest, owner?: string, enabled?: boolean) =>
    apiFetch<ManifestSummary>("/engine/manifests", {
      method: "POST",
      body: JSON.stringify({ spec, owner, enabled }),
    }),

  getManifest: (id: string) =>
    apiFetch<ManifestSummary & { spec: PipelineManifest; created_at: string; updated_at: string }>(
      `/engine/manifests/${encodeURIComponent(id)}`,
    ),

  deleteManifest: (id: string) =>
    apiFetch<{ id: string; status: string }>(
      `/engine/manifests/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),

  runManifest: (id: string, triggeredBy?: string) =>
    apiFetch<{ manifest_id: string; run_id: string; status: string; result: unknown }>(
      `/engine/manifests/${encodeURIComponent(id)}/run`,
      { method: "POST", ...(triggeredBy ? { query: { triggered_by: triggeredBy } } : {}) },
    ),

  runAdhoc: (spec: PipelineManifest) =>
    apiFetch<{ status: string; result: unknown }>("/engine/run-adhoc", {
      method: "POST",
      body: JSON.stringify(spec),
    }),

  listRuns: (params?: { manifest_id?: string; namespace?: string; status?: string; limit?: number }) =>
    apiFetch<RunSummary[]>("/engine/runs", params ? { query: params } : {}),

  getRun: (id: string) =>
    apiFetch<
      RunSummary & {
        sink_result: Record<string, unknown>;
        lineage: Record<string, unknown>;
        errors: string[];
        extras: unknown[];
        code_version_sha: string | null;
      }
    >(`/engine/runs/${encodeURIComponent(id)}`),
};
