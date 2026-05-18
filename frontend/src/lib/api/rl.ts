import { apiFetch } from "./client";

import type { TaskAccepted } from "./bots";

/**
 * Typed REST wrappers for the RL surface. Each entry resolves to a
 * spec-driven RLRuntime call on the backend; train / paper / replay
 * all go through `RLRuntime` (AGENTS.md rule 16) so client code only
 * needs to assemble the spec.
 */

export interface RLAlgo {
  key: string;
  label: string;
  framework: string;
  policy?: string;
}

export interface RLEnv {
  key: string;
  label: string;
  module: string;
  class: string;
  action_space: string;
}

export interface RLApplicationParam {
  name: string;
  type: string;
  required?: boolean;
  default?: unknown;
  enum?: unknown[];
  format?: string;
}

export interface RLApplication {
  key: string;
  label: string;
  description?: string;
  params: RLApplicationParam[];
  default_algo?: string;
  default_env?: string;
}

export interface RLRunSummary {
  id: string;
  experiment_name?: string;
  algo?: string;
  env?: string;
  status?: string;
  episodes?: number;
  mean_return?: number;
  sharpe?: number;
  started_at?: string;
  ended_at?: string;
}

export interface RLRunDetail extends RLRunSummary {
  spec_version_hash?: string;
  spec?: Record<string, unknown>;
  task_id?: string;
}

export interface RLEquityPoint {
  episode: number;
  equity: number;
}

export interface RLRewardTerm {
  step: number;
  term: string;
  value: number;
}

export interface RLActionPoint {
  step: number;
  action: string;
  count: number;
}

export const RlApi = {
  algos: (): Promise<RLAlgo[]> => apiFetch<RLAlgo[]>("/rl/algos"),
  envs: (): Promise<RLEnv[]> => apiFetch<RLEnv[]>("/rl/envs"),
  applications: (): Promise<RLApplication[]> => apiFetch<RLApplication[]>("/rl/applications"),

  startExperiment: (body: {
    application: string;
    name: string;
    algo?: string | undefined;
    env?: string | undefined;
    params?: Record<string, unknown> | undefined;
  }): Promise<TaskAccepted> =>
    apiFetch<TaskAccepted>("/rl/runs", { method: "POST", body: JSON.stringify(body) }),

  listRuns: (params?: { limit?: number; status?: string }): Promise<RLRunSummary[]> =>
    apiFetch<RLRunSummary[]>("/rl/runs", params ? { query: params } : {}),

  getRun: (id: string): Promise<RLRunDetail> =>
    apiFetch<RLRunDetail>(`/rl/runs/${encodeURIComponent(id)}`),

  cancelRun: (id: string): Promise<{ ok: boolean }> =>
    apiFetch(`/rl/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),

  runEquity: (id: string): Promise<RLEquityPoint[]> =>
    apiFetch<RLEquityPoint[]>(`/rl/runs/${encodeURIComponent(id)}/equity`),

  runRewardDecomp: (id: string): Promise<RLRewardTerm[]> =>
    apiFetch<RLRewardTerm[]>(`/rl/runs/${encodeURIComponent(id)}/reward-decomp`),

  runActions: (id: string): Promise<RLActionPoint[]> =>
    apiFetch<RLActionPoint[]>(`/rl/runs/${encodeURIComponent(id)}/actions`),
};
