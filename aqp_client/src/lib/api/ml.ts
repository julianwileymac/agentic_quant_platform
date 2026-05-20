import { apiFetch } from "./client";

import type { TaskAccepted } from "./bots";

/**
 * Typed REST wrappers for the ML training surface. Mirrors
 * `aqp.api.routes.ml` plus the lightweight workbench-flow helpers.
 */

export interface MlRunSummary {
  id: string;
  run_name?: string;
  model_kind?: string;
  status?: string;
  task_id?: string | null;
  rmse?: number;
  mae?: number;
  r2?: number;
  loss?: number;
  started_at?: string;
  ended_at?: string;
  mlflow_run_id?: string | null;
}

export interface MlModel {
  id: string;
  name: string;
  kind: string;
  version: number;
  registered_at?: string;
  metrics?: Record<string, number>;
  artifact_uri?: string | null;
}

export interface MlDataset {
  id: string;
  name: string;
  rows?: number;
  cols?: number;
  feature_set?: string;
  target?: string;
  created_at?: string;
}

export interface MlTrainBody {
  model_kind: string;
  dataset_id?: string | undefined;
  features?: string[] | undefined;
  target?: string | undefined;
  hyperparams?: Record<string, unknown> | undefined;
  run_name?: string | undefined;
}

export const MlApi = {
  runs: (params?: { limit?: number; status?: string; model_kind?: string }): Promise<MlRunSummary[]> =>
    apiFetch<MlRunSummary[]>("/ml/runs", params ? { query: params } : {}),

  getRun: (id: string): Promise<MlRunSummary> =>
    apiFetch<MlRunSummary>(`/ml/runs/${encodeURIComponent(id)}`),

  models: (): Promise<MlModel[]> => apiFetch<MlModel[]>("/ml/models"),

  datasets: (): Promise<MlDataset[]> => apiFetch<MlDataset[]>("/ml/datasets"),

  train: (body: MlTrainBody): Promise<TaskAccepted> =>
    apiFetch<TaskAccepted>("/ml/train", { method: "POST", body: JSON.stringify(body) }),

  cancelRun: (id: string): Promise<{ ok: boolean }> =>
    apiFetch(`/ml/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
};
