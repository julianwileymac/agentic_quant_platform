import { apiFetch } from "./client";

import type { TaskAccepted } from "./bots";

export interface StrategySummary {
  id: string;
  name: string;
  slug?: string;
  class?: string;
  module_path?: string;
  description?: string;
  tags?: string[];
  current_version?: number;
  created_at?: string;
  updated_at?: string;
  /** Last-30d performance metrics, when available. */
  last_sharpe?: number | null;
  last_sortino?: number | null;
  last_max_drawdown?: number | null;
  last_run_at?: string | null;
}

export interface StrategyDetail extends StrategySummary {
  config: Record<string, unknown>;
  kwargs?: Record<string, unknown>;
}

export interface StrategyVersion {
  id: string;
  strategy_id: string;
  version: number;
  spec_hash: string;
  notes?: string | null;
  created_at: string;
}

export interface CreateStrategyRequest {
  name: string;
  class: string;
  module_path: string;
  kwargs?: Record<string, unknown>;
  description?: string;
  tags?: string[];
}

function path(ref: string, suffix = ""): string {
  return `/strategies/${encodeURIComponent(ref)}${suffix}`;
}

export const strategiesApi = {
  list(params?: { tag?: string; limit?: number }): Promise<StrategySummary[]> {
    return apiFetch<StrategySummary[]>("/strategies", params ? { query: params } : {});
  },
  get(ref: string): Promise<StrategyDetail> {
    return apiFetch<StrategyDetail>(path(ref));
  },
  versions(ref: string, limit = 50): Promise<StrategyVersion[]> {
    return apiFetch<StrategyVersion[]>(path(ref, "/versions"), { query: { limit } });
  },
  create(body: CreateStrategyRequest): Promise<StrategyDetail> {
    return apiFetch<StrategyDetail>("/strategies", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  update(ref: string, body: Partial<CreateStrategyRequest>): Promise<StrategyDetail> {
    return apiFetch<StrategyDetail>(path(ref), {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  remove(ref: string): Promise<void> {
    return apiFetch<void>(path(ref), { method: "DELETE" });
  },
  runBacktest(ref: string, body?: Record<string, unknown>): Promise<TaskAccepted> {
    return apiFetch<TaskAccepted>(path(ref, "/backtest"), {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
  },
};
