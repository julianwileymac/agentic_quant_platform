/**
 * Typed client for the Phase 4 ``/analytics/*`` routes.
 *
 * The endpoints are backed by ``aqp/api/routes/analytics_portfolio.py``
 * and ``aqp/api/routes/analytics_ml.py``. Tearsheet rendering enqueues
 * a Celery task and returns ``{task_id}`` so the React side attaches
 * via the canonical ``useChatStream`` / ``useLiveStream`` pipeline.
 */
import { apiFetch } from "@/lib/api/client";

export type PortfolioMetricsResponse = {
  ok: boolean;
  metrics: Record<string, number | null>;
  n_periods: number;
  periods_per_year: number;
  risk_free_rate: number;
};

export type RollingPoint = { t: string; v: number | null };

export type PortfolioRollingResponse = {
  ok: boolean;
  window: number;
  rolling_sharpe: RollingPoint[];
  rolling_vol: RollingPoint[];
  underwater: RollingPoint[];
};

export type TearsheetEnqueueResponse = {
  ok: boolean;
  task_id: string;
  stage: string;
};

export async function getPortfolioMetrics(payload: {
  returns: number[];
  index_dates?: string[];
  risk_free_rate?: number;
  periods_per_year?: number;
}): Promise<PortfolioMetricsResponse> {
  return apiFetch("/analytics/portfolio/metrics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getPortfolioRolling(payload: {
  returns: number[];
  index_dates?: string[];
  window?: number;
  risk_free_rate?: number;
  periods_per_year?: number;
}): Promise<PortfolioRollingResponse> {
  return apiFetch("/analytics/portfolio/rolling", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function enqueuePortfolioTearsheet(payload: {
  returns: number[];
  index_dates?: string[];
  benchmark_returns?: number[];
  title?: string;
}): Promise<TearsheetEnqueueResponse> {
  return apiFetch("/analytics/portfolio/tearsheet", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export type DistributionOverlayResponse = {
  ok: boolean;
  bins: (number | null)[];
  actual: number[];
  predicted: number[];
  n_actual: number;
  n_predicted: number;
};

export async function getDistributionOverlay(payload: {
  actual: number[];
  predicted: number[];
  bins?: number;
}): Promise<DistributionOverlayResponse> {
  return apiFetch("/analytics/ml/distribution-overlay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export type DriftHeatmapResponse = {
  ok: boolean;
  matrix: (number | null)[][];
  x_labels: string[];
  y_labels: string[];
  shape: [number, number];
};

export async function getDriftHeatmap(payload: {
  matrix: number[][];
  x_labels?: string[];
  y_labels?: string[];
}): Promise<DriftHeatmapResponse> {
  return apiFetch("/analytics/ml/drift-heatmap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
