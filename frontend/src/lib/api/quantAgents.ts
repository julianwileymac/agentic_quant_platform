import { apiFetch } from "./client";

/**
 * Typed REST wrappers for ``/quant-agents/*`` — Phase 4 of the
 * hybrid agentic-RL rollout. Drives the AlphaResearcher +
 * StrategyExecutor agents plus the symbolic alpha AST sandbox.
 */

export interface FactorCompilePreviewRequest {
  formula: string;
  name?: string;
}

export interface FactorCompilePreviewResponse {
  ok: boolean;
  formula: string;
  name?: string | null;
  used_operators: string[];
  used_fields: string[];
  error?: string | null;
}

export interface AlphaProposeRequest {
  intent: string;
  vt_symbol?: string;
  recent_factor_summary?: Array<Record<string, unknown>>;
  agent_spec_name?: string;
}

export interface AlphaProposeResponse {
  name: string;
  formula: string;
  rationale: string;
  expected_horizon_bars?: number | null;
  expected_direction?: string | null;
  raw_output?: Record<string, unknown> | null;
}

export interface AlphaEvaluateRequest {
  name?: string;
  formula: string;
  rationale?: string;
  vt_symbols?: string[];
  sharpe_weight?: number;
  drawdown_weight?: number;
  turnover_weight?: number;
}

export interface AlphaEvaluateResponse {
  name: string;
  formula: string;
  rationale: string;
  compiled: boolean;
  metrics: Record<string, number>;
  reward: number;
  rejection_reason?: string | null;
}

export interface StrategyDispatchRequest {
  intent: "train" | "evaluate" | "paper" | "replay" | "walk_forward";
  experiment_slug: string;
  window?: Record<string, unknown>;
  kill_switch_check?: boolean;
  agent_spec_name?: string;
}

export interface StrategyDispatchResponse {
  intent: string;
  experiment_slug: string;
  rationale: string;
  go: boolean;
  runtime_result: Record<string, unknown>;
  error?: string | null;
}

export interface QuantAgentSpec {
  name: string;
  role?: string | null;
  description?: string | null;
  model?: Record<string, unknown> | null;
  tools: string[];
}

export const QuantAgentsApi = {
  compilePreview: (body: FactorCompilePreviewRequest) =>
    apiFetch<FactorCompilePreviewResponse>("/quant-agents/factor/compile-preview", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }),

  alphaPropose: (body: AlphaProposeRequest) =>
    apiFetch<AlphaProposeResponse>("/quant-agents/alpha-researcher/propose", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }),

  alphaEvaluate: (body: AlphaEvaluateRequest) =>
    apiFetch<AlphaEvaluateResponse>("/quant-agents/alpha-researcher/evaluate", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }),

  strategyDispatch: (body: StrategyDispatchRequest) =>
    apiFetch<StrategyDispatchResponse>("/quant-agents/strategy-executor/dispatch", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    }),

  listSpecs: () => apiFetch<QuantAgentSpec[]>("/quant-agents/specs"),
};
