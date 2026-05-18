import { apiFetch } from "@/lib/api/client";

export interface FlowSchema {
  name: string;
  namespace: string;
  label: string;
  description: string;
  tags: string[];
  params_schema: Record<string, unknown>;
  requires_dataset: boolean;
  output_kind: string;
  optional_dependencies: string[];
}

export interface FlowResult {
  flow: string;
  metrics: Record<string, unknown>;
  rows: Array<Record<string, unknown>>;
  artifacts: Record<string, unknown>;
  chart: { data: unknown[]; layout: Record<string, unknown> } | null;
  error?: string | null;
  iceberg_identifier?: string | null;
}

export interface DatasetRef {
  iceberg_identifier?: string | null;
  dataset_cfg?: Record<string, unknown> | null;
  columns?: string[];
  limit?: number | null;
}

export interface PreviewRequest extends DatasetRef {
  params: Record<string, unknown>;
}

export interface RunSummary {
  id: string;
  spec_id?: string | null;
  version_id?: string | null;
  target: string;
  task_id?: string | null;
  status: string;
  dataset_descriptor?: string | null;
  iceberg_result_table?: string | null;
  error?: string | null;
  started_at: string;
  ended_at?: string | null;
  result_summary: Record<string, unknown>;
}

export interface StepResultSummary {
  id: string;
  step_alias: string;
  flow: string;
  status: string;
  params_json: Record<string, unknown>;
  metrics_json: Record<string, unknown>;
  artifact_uri?: string | null;
  duration_ms?: number | null;
  error?: string | null;
  created_at: string;
}

export interface RunDetail extends RunSummary {
  steps: StepResultSummary[];
}

export interface SpecSummary {
  id: string;
  name: string;
  slug: string;
  kind: string;
  description?: string | null;
  current_version: number;
  status: string;
  annotations: string[];
  created_at: string;
  updated_at: string;
}

export interface SpecVersionSummary {
  id: string;
  version: number;
  spec_hash: string;
  created_at: string;
  notes?: string | null;
}

export interface SpecDetail extends SpecSummary {
  payload: Record<string, unknown>;
  versions: SpecVersionSummary[];
}

export interface DatasetColumn {
  name: string;
  dtype: string;
}

export async function listAnalysisFlows(namespace?: string): Promise<FlowSchema[]> {
  const init = namespace ? { query: { namespace } } : {};
  return apiFetch<FlowSchema[]>("/analysis/flows", init);
}

export async function previewAnalysisFlow(
  flow: string,
  body: PreviewRequest,
): Promise<FlowResult> {
  return apiFetch<FlowResult>(`/analysis/flows/${flow}/preview`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listAnalysisSpecs(limit = 100): Promise<SpecSummary[]> {
  return apiFetch<SpecSummary[]>("/analysis/specs", { query: { limit } });
}

export async function getAnalysisSpec(slug: string): Promise<SpecDetail> {
  return apiFetch<SpecDetail>(`/analysis/specs/${slug}`);
}

export async function saveAnalysisSpec(spec: Record<string, unknown>): Promise<SpecSummary> {
  return apiFetch<SpecSummary>("/analysis/specs", {
    method: "POST",
    body: JSON.stringify({ spec }),
  });
}

export async function runAnalysisSpec(
  slug: string,
  target = "run",
): Promise<{ task_id: string; stream_url?: string | null }> {
  return apiFetch<{ task_id: string; stream_url?: string | null }>(
    `/analysis/specs/${slug}/run`,
    {
      method: "POST",
      body: JSON.stringify({ target }),
    },
  );
}

export async function listAnalysisRuns(opts?: {
  limit?: number;
  status?: string;
  spec_id?: string;
}): Promise<RunSummary[]> {
  return apiFetch<RunSummary[]>("/analysis/runs", { query: opts ?? {} });
}

export async function getAnalysisRun(runId: string): Promise<RunDetail> {
  return apiFetch<RunDetail>(`/analysis/runs/${runId}`);
}

export async function getAnalysisStepResults(
  runId: string,
  step: string,
  limit = 200,
): Promise<{
  step: string;
  rows: Array<Record<string, unknown>>;
  metrics: Record<string, unknown>;
  artifact_uri: string | null;
}> {
  return apiFetch(`/analysis/runs/${runId}/results/${step}`, {
    query: { limit },
  });
}

export async function getDatasetColumns(identifier: string): Promise<{
  identifier: string;
  columns: DatasetColumn[];
}> {
  return apiFetch("/analysis/datasets/columns", { query: { identifier } });
}
