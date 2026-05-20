import { apiFetch } from "./client";

/**
 * Typed client for the 7 `/api/infra/*` REST endpoints backing the
 * Infrastructure Dashboard panes. No secrets values cross this wire
 * — `infraSecrets()` returns metadata only.
 */

export interface WorkspaceStatus {
  id: string;
  slug: string;
  name: string;
  environment: string;
  state_backend: string;
  tenant_org_id?: string | null;
  last_apply_at?: string | null;
  last_run_status?: string | null;
  last_run_kind?: string | null;
  state_serial?: number | null;
  resource_count?: number | null;
  drift?: boolean;
}

export interface InfraStatus {
  workspaces: WorkspaceStatus[];
  totals: {
    workspaces: number;
    runs: number;
    drift_alert: boolean;
  };
  generated_at?: string;
}

export interface QueueRow {
  name: string;
  depth: number;
  current_replicas: number | null;
}

export interface QueueDepths {
  queues: QueueRow[];
  generated_at?: string;
}

export interface PipelineAdapter {
  name: string;
  last_run_at?: string | null;
  runs_recent?: number | null;
  status?: string | null;
  [key: string]: unknown;
}

export interface PipelineStatus {
  adapters: PipelineAdapter[];
  parquet?: {
    manifest_count?: number | null;
    pipeline_run_count?: number | null;
    [key: string]: unknown;
  };
  alembic_revision?: string | null;
  generated_at?: string;
}

export interface SecretStoreInfo {
  alias: string;
  kind: string;
  priority: number;
}

export interface SecretsStatus {
  stores: SecretStoreInfo[];
  generated_at?: string;
}

export interface K8sPodInfo {
  name: string;
  namespace?: string;
  phase?: string;
  node?: string;
  pod_ip?: string;
  started_at?: string;
  containers?: string[];
  labels?: Record<string, string>;
  [key: string]: unknown;
}

export interface K8sNamespacePods {
  pods: K8sPodInfo[];
  adapter_available: boolean;
  namespace?: string;
  generated_at?: string;
}

export interface CanarySetPayload {
  weight: number;
  namespace?: string;
  config_map_name?: string;
}

export const infraApi = {
  status: async (): Promise<InfraStatus> => apiFetch("/api/infra/status"),
  queues: async (): Promise<QueueDepths> => apiFetch("/api/infra/queues"),
  pipeline: async (): Promise<PipelineStatus> => apiFetch("/api/infra/pipeline"),
  secrets: async (): Promise<SecretsStatus> => apiFetch("/api/infra/secrets"),
  k8sNamespace: async (
    namespace: string,
    label_selector?: string,
  ): Promise<K8sNamespacePods> =>
    apiFetch(`/api/infra/k8s/${encodeURIComponent(namespace)}`, {
      query: label_selector ? { label_selector } : {},
    }),
  canarySet: async (
    payload: CanarySetPayload,
  ): Promise<{
    weight: number;
    config_map_name: string;
    namespace: string;
    applied: unknown;
  }> =>
    apiFetch("/api/infra/canary", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
