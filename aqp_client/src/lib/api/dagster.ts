import { apiFetch } from "./client";

export interface DagsterStatus {
  graphql_url: string | null;
  code_location: string;
  module_path: string;
  grpc_host: string;
  grpc_port: number;
  repository_selector?: {
    repositoryLocationName: string;
    repositoryName: string;
  };
}

export interface DagsterAssetNode {
  key?: string[];
  assetKey?: { path: string[] };
  description?: string | null;
  groupName?: string | null;
  computeKind?: string | null;
  isPartitioned?: boolean;
}

export interface DagsterRunSummary {
  runId: string;
  pipelineName: string;
  status: string;
  startTime?: number | null;
  endTime?: number | null;
}

export interface DagsterScheduleSummary {
  name: string;
  cronSchedule?: string;
  executionTimezone?: string | null;
  scheduleState?: { id?: string; selectorId?: string; status?: string };
}

export interface DagsterSensorSummary {
  name: string;
  sensorState?: { id?: string; selectorId?: string; status?: string };
}

export const dagsterApi = {
  status: () => apiFetch<DagsterStatus>("/dagster/status"),

  listAssets: () =>
    apiFetch<{ source: string; asset_nodes: DagsterAssetNode[] }>("/dagster/assets"),

  listRuns: (limit = 25) =>
    apiFetch<{ source: string; runs: DagsterRunSummary[]; error?: string }>(
      "/dagster/runs",
      { query: { limit } },
    ),

  trigger: (assetKeys: string[][], runConfig: Record<string, unknown> = {}) =>
    apiFetch<Record<string, unknown>>("/dagster/trigger", {
      method: "POST",
      body: JSON.stringify({ asset_keys: assetKeys, run_config: runConfig }),
    }),

  listSchedules: () => apiFetch<{ schedules: DagsterScheduleSummary[] }>("/dagster/schedules"),
  listSensors: () => apiFetch<{ sensors: DagsterSensorSummary[] }>("/dagster/sensors"),

  startSchedule: (name: string) =>
    apiFetch<Record<string, unknown>>(`/dagster/schedules/${encodeURIComponent(name)}/start`, {
      method: "POST",
    }),

  stopSchedule: (name: string) =>
    apiFetch<Record<string, unknown>>(`/dagster/schedules/${encodeURIComponent(name)}/stop`, {
      method: "POST",
    }),

  startSensor: (name: string) =>
    apiFetch<Record<string, unknown>>(`/dagster/sensors/${encodeURIComponent(name)}/start`, {
      method: "POST",
    }),

  stopSensor: (name: string) =>
    apiFetch<Record<string, unknown>>(`/dagster/sensors/${encodeURIComponent(name)}/stop`, {
      method: "POST",
    }),
};
