import { apiFetch } from "./client";

/**
 * Typed REST wrappers for the additive `/workflows` orchestration
 * control plane.
 *
 * All routes return 503 when `AQP_ORCHESTRATION_STUDIO_ENABLED` is
 * off. Callers should surface that as a "studio disabled" banner
 * rather than treating it as a generic error — see
 * `docs/orchestration-refactor-rollout.md`.
 */

export interface WorkflowSpecSummary {
  name: string;
  adapter: string;
  description?: string;
  snapshot_hash?: string;
  annotations?: string[];
  template_target?: string;
}

export interface WorkflowSpecDetail extends WorkflowSpecSummary {
  payload: Record<string, unknown>;
}

export interface WorkflowSpecVersion {
  id: string;
  version: number;
  spec_hash: string;
  notes: string | null;
  created_at: string | null;
}

export interface WorkflowRunSummary {
  id: string;
  workflow_spec_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  cost_usd: number;
  duration_ms: number | null;
  halted: boolean;
  error: string | null;
}

export interface WorkflowRunBreadcrumb {
  adapter: string;
  node: string;
  status: string;
  duration_ms?: number;
  [key: string]: unknown;
}

export interface WorkflowRunDetail extends WorkflowRunSummary {
  spec_version_id: string | null;
  inputs: Record<string, unknown>;
  final_state: Record<string, unknown>;
  breadcrumbs: WorkflowRunBreadcrumb[];
}

export interface WorkflowRunRequest {
  spec_name: string;
  inputs?: Record<string, unknown>;
}

export interface WorkflowHaltRequest {
  run_id?: string;
  reason?: string;
}

export interface TaskAccepted {
  task_id: string;
  status: string;
}

export async function listWorkflows(): Promise<WorkflowSpecSummary[]> {
  return apiFetch<WorkflowSpecSummary[]>("/workflows");
}

export async function getWorkflow(name: string): Promise<WorkflowSpecDetail> {
  return apiFetch<WorkflowSpecDetail>(`/workflows/${encodeURIComponent(name)}`);
}

export async function listWorkflowVersions(
  name: string,
): Promise<WorkflowSpecVersion[]> {
  return apiFetch<WorkflowSpecVersion[]>(
    `/workflows/${encodeURIComponent(name)}/versions`,
  );
}

export async function runWorkflow(
  name: string,
  body: WorkflowRunRequest,
): Promise<TaskAccepted> {
  return apiFetch<TaskAccepted>(`/workflows/${encodeURIComponent(name)}/run`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function replayWorkflowRun(
  runId: string,
): Promise<TaskAccepted> {
  return apiFetch<TaskAccepted>(
    `/workflows/runs/${encodeURIComponent(runId)}/replay`,
    {
      method: "POST",
    },
  );
}

export async function listWorkflowRuns(
  params: { spec_name?: string; status?: string; limit?: number } = {},
): Promise<WorkflowRunSummary[]> {
  const query = new URLSearchParams();
  if (params.spec_name) query.set("spec_name", params.spec_name);
  if (params.status) query.set("status", params.status);
  if (params.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return apiFetch<WorkflowRunSummary[]>(
    `/workflows/runs${qs ? `?${qs}` : ""}`,
  );
}

export async function getWorkflowRun(runId: string): Promise<WorkflowRunDetail> {
  return apiFetch<WorkflowRunDetail>(
    `/workflows/runs/${encodeURIComponent(runId)}`,
  );
}

export async function haltWorkflows(
  body: WorkflowHaltRequest = {},
): Promise<{ ok: boolean; halted_count: number; halted: unknown[] }> {
  return apiFetch<{ ok: boolean; halted_count: number; halted: unknown[] }>(
    `/workflows/halt`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}
