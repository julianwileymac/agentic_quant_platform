import { apiFetch } from "./client";

import type { TaskAccepted } from "./bots";

/**
 * Typed REST wrappers for backtest runs. The legacy webui hits
 * `/backtest/runs/{id}/plot/equity` directly; this thin wrapper
 * normalises the plotly-shaped response into a simple
 * `{timestamp, value}` series the new EquityChart consumes.
 */

export interface BacktestRunSummary {
  id: string;
  run_name?: string;
  engine?: string;
  strategy?: string;
  status?: string;
  pnl_total?: number;
  sharpe?: number;
  sortino?: number;
  calmar?: number;
  max_drawdown?: number;
  win_rate?: number;
  profit_factor?: number;
  total_return?: number;
  cagr?: number;
  final_equity?: number;
  started_at?: string;
  ended_at?: string;
}

export interface BacktestRunDetail extends BacktestRunSummary {
  start?: string | null;
  end?: string | null;
  dataset_hash?: string | null;
  config?: Record<string, unknown>;
}

export interface BacktestTrade {
  ts?: string;
  vt_symbol?: string;
  side?: string;
  qty?: number;
  price?: number;
  pnl?: number;
}

export interface PlotResponse {
  data?: Array<{ x?: string[]; y?: number[]; name?: string; type?: string }>;
}

export interface EquityPoint {
  timestamp: string;
  value: number;
}

/** Convert a `/plot/equity` response into the EquityChart shape. */
export function plotToSeries(plot: PlotResponse | undefined): EquityPoint[] {
  const trace = plot?.data?.find((t) => Array.isArray(t.x) && Array.isArray(t.y));
  if (!trace || !trace.x || !trace.y) return [];
  const xs = trace.x;
  const ys = trace.y;
  const n = Math.min(xs.length, ys.length);
  const out: EquityPoint[] = [];
  for (let i = 0; i < n; i += 1) {
    out.push({ timestamp: xs[i] ?? String(i), value: Number(ys[i]) });
  }
  return out;
}

export const BacktestApi = {
  list(params?: { limit?: number }): Promise<BacktestRunSummary[] | { items: BacktestRunSummary[] }> {
    return apiFetch<BacktestRunSummary[] | { items: BacktestRunSummary[] }>(
      "/backtest/runs",
      params ? { query: params } : {},
    );
  },

  get(id: string): Promise<BacktestRunDetail> {
    return apiFetch<BacktestRunDetail>(`/backtest/runs/${encodeURIComponent(id)}`);
  },

  trades(id: string, limit = 500): Promise<BacktestTrade[]> {
    return apiFetch<BacktestTrade[]>(`/backtest/runs/${encodeURIComponent(id)}/trades`, {
      query: { limit },
    });
  },

  equityPlot(id: string): Promise<PlotResponse> {
    return apiFetch<PlotResponse>(`/backtest/runs/${encodeURIComponent(id)}/plot/equity`);
  },

  drawdownPlot(id: string): Promise<PlotResponse> {
    return apiFetch<PlotResponse>(`/backtest/runs/${encodeURIComponent(id)}/plot/drawdown`);
  },

  start(body: { strategy: Record<string, unknown>; run_name?: string; session?: Record<string, unknown> }): Promise<TaskAccepted> {
    return apiFetch<TaskAccepted>("/backtest/runs", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  cancel(id: string): Promise<{ ok: boolean }> {
    return apiFetch(`/backtest/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
  },

  /**
   * Phase 4 — kick off the agent-driven iterative optimisation loop.
   * The Celery task warm-starts from regime memory, mutates params
   * via the parameter_mutator AgentSpec, and stops when target Sharpe
   * is reached or max_iterations is exhausted. Returns the task id
   * so the SPA can stream progress over the existing progress bus.
   */
  iterate(body: {
    strategy_id: string;
    base_config: Record<string, unknown>;
    target_sharpe: number;
    max_iterations?: number;
    regime?: string;
  }): Promise<TaskAccepted> {
    return apiFetch<TaskAccepted>("/backtest/iterate", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};
