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

export interface MlServingSession {
  session_id: string;
  model_alias: string;
  model_class: string;
  max_batch_size: number;
  max_wait_ms: number;
  halted: boolean;
  pending: number;
  served: number;
  started_at: string;
}

export interface MlSkillSummary {
  name: string;
  description: string;
  kind: string;
  n_steps: number;
  annotations: string[];
  spec_hash: string;
}

export interface MlSkillDescribe extends MlSkillSummary {
  steps: Array<{
    name: string;
    interface_kind: string;
    model_ref: string;
    output_alias?: string;
  }>;
  guardrails: {
    rule_pack: string;
    cost_budget_usd: number;
    max_runtime_ms: number;
    require_workspace: boolean;
  };
}

export interface MlPullBody {
  source: "huggingface" | "torchhub";
  model_name: string;
  revision?: string;
  include_examples?: boolean;
}

export interface MlProductionizeBody {
  target: "onnx" | "tensorrt" | "torchscript" | "quantize";
  compile_kwargs?: Record<string, unknown>;
  output_path?: string;
}

export interface MlCacheWarmBody {
  cache_key?: string;
}

export interface MlSkillRunBody {
  inputs: Record<string, unknown>;
  experiment_id?: string;
  test_id?: string;
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

  // ----- MLOps service additions (initial slice) -----
  pull: (body: MlPullBody): Promise<TaskAccepted> =>
    apiFetch<TaskAccepted>("/ml/models/pull", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  productionize: (modelVersionId: string, body: MlProductionizeBody): Promise<TaskAccepted> =>
    apiFetch<TaskAccepted>(
      `/ml/models/${encodeURIComponent(modelVersionId)}/productionize`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  cacheWarm: (modelVersionId: string, body: MlCacheWarmBody = {}): Promise<{ cached: unknown; load: unknown }> =>
    apiFetch(
      `/ml/models/${encodeURIComponent(modelVersionId)}/cache/warm`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  servingSessions: (): Promise<{ sessions: MlServingSession[]; n_sessions: number }> =>
    apiFetch("/ml/serving/sessions"),

  haltAllServing: (): Promise<{ halted: number }> =>
    apiFetch("/ml/serving/halt-all", { method: "POST" }),

  // ----- Skill registry -----
  skills: (): Promise<MlSkillSummary[]> => apiFetch("/ml/skills"),

  describeSkill: (name: string): Promise<MlSkillDescribe> =>
    apiFetch(`/ml/skills/${encodeURIComponent(name)}`),

  runSkill: (name: string, body: MlSkillRunBody): Promise<TaskAccepted> =>
    apiFetch<TaskAccepted>(
      `/ml/skills/${encodeURIComponent(name)}/run`,
      { method: "POST", body: JSON.stringify(body) },
    ),
};
