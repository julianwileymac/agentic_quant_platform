import { apiFetch } from "./client";

/**
 * Typed REST wrappers for the `/agents` surface — spec-driven
 * agent registry, runs, evaluations, proposals.
 */

/**
 * Which UI flow the Agent Templates page should open for a spec.
 *
 * Mirrors the `template_target` literal on
 * `aqp.agents.spec.AgentSpec`. New backends populate the field on
 * `/agents/specs`; older ones omit it, in which case we fall back to
 * "utility" client-side so deep-links degrade gracefully.
 */
export type AgentTemplateTarget =
  | "backtest"
  | "research"
  | "selection"
  | "trader"
  | "analysis"
  | "live"
  | "paper"
  | "utility";

export interface AgentSpecSummary {
  name: string;
  role: string;
  description?: string;
  snapshot_hash?: string;
  n_tools?: number;
  n_rag_clauses?: number;
  memory_kind?: string;
  annotations?: string[];
  template_target?: AgentTemplateTarget;
  updated_at?: string | null;
  run_count?: number | null;
}

export interface AgentSpecDetail extends AgentSpecSummary {
  payload: Record<string, unknown>;
}

export interface AgentSpecVersion {
  id: string;
  version: number;
  spec_hash: string;
  notes: string | null;
  created_at: string | null;
}

export interface AgentRunSummary {
  id: string;
  spec_name?: string;
  spec_version_hash?: string;
  status?: string;
  cost_usd?: number;
  tokens_in?: number;
  tokens_out?: number;
  n_calls?: number;
  n_tool_calls?: number;
  n_rag_hits?: number;
  guardrail_failures?: number;
  started_at?: string | null;
  completed_at?: string | null;
  ended_at?: string | null;
  error?: string | null;
}

export interface AgentRunStep {
  seq: number;
  kind: string;
  name: string;
  inputs: Record<string, unknown>;
  output: Record<string, unknown>;
  cost_usd: number;
  duration_ms: number | null;
  error: string | null;
  created_at: string | null;
}

export interface AgentRunDetail extends AgentRunSummary {
  inputs?: Record<string, unknown>;
  output?: Record<string, unknown>;
  spec_version_id?: string | null;
  steps?: AgentRunStep[];
}

export interface AgentDecision {
  id: string;
  run_id?: string;
  vt_symbol?: string;
  ts?: string;
  action?: string;
  size_pct?: number;
  confidence?: number;
  rationale?: string;
  provider?: string;
}

export interface AgentReflection {
  id: string;
  run_id?: string;
  ts?: string;
  text: string;
  tags?: string[];
}

export interface AgentEvaluation {
  id: string;
  spec_name: string;
  eval_set_name: string;
  n_cases: number;
  n_passed: number;
  aggregate: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
}

export const AgentsApi = {
  listSpecs: (): Promise<AgentSpecSummary[]> => apiFetch<AgentSpecSummary[]>("/agents/specs"),

  getSpec: (name: string): Promise<AgentSpecDetail> =>
    apiFetch<AgentSpecDetail>(`/agents/specs/${encodeURIComponent(name)}`),

  listSpecVersions: (name: string): Promise<AgentSpecVersion[]> =>
    apiFetch<AgentSpecVersion[]>(`/agents/specs/${encodeURIComponent(name)}/versions`),

  listRuns: (params?: { spec_name?: string; status?: string; limit?: number }): Promise<AgentRunSummary[]> =>
    apiFetch<AgentRunSummary[]>("/agents/runs/v2", params ? { query: params } : {}),

  getRun: (id: string): Promise<AgentRunDetail> =>
    apiFetch<AgentRunDetail>(`/agents/runs/v2/${encodeURIComponent(id)}`),

  /**
   * Cancel an in-flight run. The agents router itself does not expose
   * a cancel endpoint, so we route through the monitoring router which
   * revokes the underlying Celery task by id.
   */
  cancelRun: (taskId: string, terminate = true): Promise<{ ok: boolean; task_id: string }> =>
    apiFetch(`/monitoring/runs/${encodeURIComponent(taskId)}/revoke`, {
      method: "POST",
      body: JSON.stringify({ terminate, signal: "SIGTERM" }),
    }),

  runDecisions: (id: string): Promise<AgentDecision[]> =>
    apiFetch<AgentDecision[]>(`/agents/runs/v2/${encodeURIComponent(id)}/decisions`),

  runReflections: (id: string): Promise<AgentReflection[]> =>
    apiFetch<AgentReflection[]>(`/agents/runs/v2/${encodeURIComponent(id)}/reflections`),

  listEvaluations: (params?: { spec_name?: string; limit?: number }): Promise<AgentEvaluation[]> =>
    apiFetch<AgentEvaluation[]>("/agents/evaluations", params ? { query: params } : {}),

  /**
   * Run a spec synchronously and return the populated detail. Mirrors
   * `POST /agents/runs/v2/sync` on the backend.
   */
  runSpecSync: (spec_name: string, inputs: Record<string, unknown>): Promise<AgentRunDetail> =>
    apiFetch<AgentRunDetail>("/agents/runs/v2/sync", {
      method: "POST",
      body: JSON.stringify({ spec_name, inputs }),
    }),

  replayRun: (id: string): Promise<AgentRunDetail> =>
    apiFetch<AgentRunDetail>(`/agents/runs/v2/${encodeURIComponent(id)}/replay`, {
      method: "POST",
    }),

  /** Halt every running spec-driven agent run (kill-switch fan-out). */
  haltAll: (): Promise<{ stopped: number; task_ids: string[] }> =>
    apiFetch(`/agents/halt`, { method: "POST" }),
};

/** Legacy alias kept so existing webui-style imports compile unchanged. */
export type AgentRunV2Detail = AgentRunDetail;
export type AgentRunV2Summary = AgentRunSummary;
export type AgentRunV2Step = AgentRunStep;
