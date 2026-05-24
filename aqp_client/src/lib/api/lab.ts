import { apiFetch } from "./client";

/**
 * Typed REST wrappers for the additive `/lab` four-mode workspace
 * (EDA / Testing / Evaluation / Simulation).
 *
 * All routes return 503 when `AQP_LAB_ENABLED` is off. The route file
 * is mounted behind `settings.aqp_lab_enabled` in `aqp/api/main.py`.
 */

export type LabMode = "eda" | "testing" | "evaluation" | "simulation";

export type LabRunStatus =
  | "pending"
  | "queued"
  | "running"
  | "done"
  | "error"
  | "cancelled"
  | "halted";

export type LabNodeStatus =
  | "pending"
  | "queued"
  | "running"
  | "done"
  | "error"
  | "cached"
  | "skipped";

export interface LabPort {
  name: string;
  dtype: string;
  optional?: boolean;
  description?: string | null;
}

export interface LabNodeRuntime {
  target: "celery" | "dagster" | "marimo_cell" | "inline";
  queue?: string;
  image?: string | null;
  timeout_s?: number;
  resources?: Record<string, string>;
}

export interface LabNodeType {
  alias: string;
  label: string;
  description: string;
  accent?: string | null;
  inputs: LabPort[];
  outputs: LabPort[];
  runtime: LabNodeRuntime;
  executor: string;
  /**
   * JSON Schema for the node's params (rendered via RJSF). When
   * the backend can't generate a schema (the NodeType has no
   * matching Pydantic model in aqp/lab/params_models.py), this is
   * null and the inspector falls back to a JSON-text editor.
   */
  params_schema?: Record<string, unknown> | null;
}

export interface LabPaletteCategory {
  name: string;
  items: LabNodeType[];
}

export interface LabCatalogResponse {
  categories: LabPaletteCategory[];
  modes: LabMode[];
  total_nodes: number;
}

export interface LabEdgeSpec {
  id?: string;
  source: string;
  target: string;
  source_port?: string;
  target_port?: string;
  dtype?: string | null;
}

export interface LabNodeSpec {
  id?: string;
  type: string;
  label?: string;
  category:
    | "DataSource"
    | "Transformation"
    | "Feature"
    | "Alpha"
    | "Model"
    | "Strategy"
    | "Math"
    | "Labeler"
    | "Output"
    | "Agent";
  position?: [number, number];
  inputs?: LabPort[];
  outputs?: LabPort[];
  params?: Record<string, unknown>;
  runtime?: LabNodeRuntime;
  snapshot_inputs?: boolean;
  notes?: string | null;
}

export interface LabGraphSpec {
  name?: string;
  description?: string;
  mode: LabMode;
  nodes: LabNodeSpec[];
  edges: LabEdgeSpec[];
  mode_config?: Record<string, unknown>;
  parent_graph_id?: string | null;
  annotations?: string[];
}

export interface LabGraphCreate {
  lab_id: string;
  name?: string;
  description?: string;
  spec: LabGraphSpec;
  parent_graph_id?: string | null;
  project_id?: string | null;
}

export interface LabGraphPatch {
  name?: string;
  description?: string;
  spec?: LabGraphSpec;
  archive?: boolean;
}

export interface LabGraphOut {
  id: string;
  lab_id: string;
  name: string;
  description?: string | null;
  mode: LabMode;
  spec: Record<string, unknown>;
  content_hash: string;
  parent_graph_id?: string | null;
  data_snapshot: Record<string, unknown>;
  code_snapshot?: string | null;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LabRunOut {
  id: string;
  graph_id: string;
  lab_id?: string | null;
  mode: LabMode;
  status: LabRunStatus;
  session_id?: string | null;
  task_id?: string | null;
  content_hash: string;
  metrics: Record<string, unknown>;
  result_summary: Record<string, unknown>;
  error?: string | null;
  halted: boolean;
  duration_ms?: number | null;
  started_at: string;
  ended_at?: string | null;
}

export interface LabNodeRunOut {
  node_id: string;
  node_type: string;
  status: LabNodeStatus;
  metrics: Record<string, unknown>;
  output_locator: Record<string, unknown>;
  duration_ms?: number | null;
  error?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
}

export interface LabArtifactOut {
  id: string;
  node_id?: string | null;
  kind: string;
  uri: string;
  size_bytes?: number | null;
  content_hash?: string | null;
  created_at: string;
}

export interface LabRunSubmitRequest {
  inline?: boolean;
  session_id?: string | null;
}

export interface LabHaltAllResponse {
  halted: number;
}

// ---------------------------------------------------------------------------
// Catalog (palette source-of-truth)
// ---------------------------------------------------------------------------

export async function fetchLabCatalog(): Promise<LabCatalogResponse> {
  return apiFetch<LabCatalogResponse>("/lab/catalog/node-types");
}

// ---------------------------------------------------------------------------
// Graphs
// ---------------------------------------------------------------------------

export async function createLabGraph(body: LabGraphCreate): Promise<LabGraphOut> {
  return apiFetch<LabGraphOut>("/lab/graphs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listLabGraphs(
  labId: string,
  options: { mode?: LabMode; includeArchived?: boolean; limit?: number } = {},
): Promise<LabGraphOut[]> {
  const qs = new URLSearchParams({ lab_id: labId });
  if (options.mode) qs.set("mode", options.mode);
  if (options.includeArchived) qs.set("include_archived", "true");
  if (options.limit) qs.set("limit", String(options.limit));
  return apiFetch<LabGraphOut[]>(`/lab/graphs?${qs.toString()}`);
}

export async function getLabGraph(graphId: string): Promise<LabGraphOut> {
  return apiFetch<LabGraphOut>(`/lab/graphs/${encodeURIComponent(graphId)}`);
}

export async function patchLabGraph(
  graphId: string,
  patch: LabGraphPatch,
): Promise<LabGraphOut> {
  return apiFetch<LabGraphOut>(`/lab/graphs/${encodeURIComponent(graphId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteLabGraph(graphId: string): Promise<void> {
  await apiFetch<void>(`/lab/graphs/${encodeURIComponent(graphId)}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export async function submitLabRun(
  graphId: string,
  body: LabRunSubmitRequest = {},
): Promise<LabRunOut> {
  return apiFetch<LabRunOut>(`/lab/graphs/${encodeURIComponent(graphId)}/runs`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface RunSingleNodeRequest {
  upstream_locators?: Record<string, unknown>;
  session_id?: string | null;
}

export interface RunSingleNodeResponse {
  run_id: string;
  node_id: string;
  task_id: string;
  status: LabRunStatus | "queued";
  duration_ms?: number | null;
  output_locator?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  error?: string | null;
}

/** Dispatch a single node from a persisted graph through Celery. */
export async function runSingleLabNode(
  graphId: string,
  nodeId: string,
  body: RunSingleNodeRequest = {},
): Promise<RunSingleNodeResponse> {
  return apiFetch<RunSingleNodeResponse>(
    `/lab/graphs/${encodeURIComponent(graphId)}/nodes/${encodeURIComponent(nodeId)}/run`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export interface ListLabRunsOptions {
  labId?: string;
  graphId?: string;
  mode?: LabMode;
  status?: LabRunStatus;
  limit?: number;
}

export async function listLabRuns(
  options: ListLabRunsOptions = {},
): Promise<LabRunOut[]> {
  const qs = new URLSearchParams();
  if (options.labId) qs.set("lab_id", options.labId);
  if (options.graphId) qs.set("graph_id", options.graphId);
  if (options.mode) qs.set("mode", options.mode);
  if (options.status) qs.set("status", options.status);
  if (options.limit) qs.set("limit", String(options.limit));
  const path = qs.toString() ? `/lab/runs?${qs.toString()}` : "/lab/runs";
  return apiFetch<LabRunOut[]>(path);
}

export interface ReproduceRunResponse {
  graph_id: string;
  new_run_id: string;
  new_task_id: string;
  content_hash: string;
  code_snapshot_matches: boolean;
  data_snapshot_matches: boolean;
}

export async function reproduceLabRun(runId: string): Promise<ReproduceRunResponse> {
  return apiFetch<ReproduceRunResponse>(
    `/lab/runs/${encodeURIComponent(runId)}/reproduce`,
    { method: "POST" },
  );
}

export async function getLabRun(runId: string): Promise<LabRunOut> {
  return apiFetch<LabRunOut>(`/lab/runs/${encodeURIComponent(runId)}`);
}

export async function listLabRunNodes(runId: string): Promise<LabNodeRunOut[]> {
  return apiFetch<LabNodeRunOut[]>(
    `/lab/runs/${encodeURIComponent(runId)}/nodes`,
  );
}

export async function listLabRunArtifacts(
  runId: string,
): Promise<LabArtifactOut[]> {
  return apiFetch<LabArtifactOut[]>(
    `/lab/runs/${encodeURIComponent(runId)}/artifacts`,
  );
}

export async function cancelLabRun(runId: string): Promise<LabRunOut> {
  return apiFetch<LabRunOut>(
    `/lab/runs/${encodeURIComponent(runId)}/cancel`,
    {
      method: "POST",
    },
  );
}

// ---------------------------------------------------------------------------
// Kill switch
// ---------------------------------------------------------------------------

export async function haltAllLabRuns(): Promise<LabHaltAllResponse> {
  return apiFetch<LabHaltAllResponse>("/lab/halt-all", { method: "POST" });
}

// ---------------------------------------------------------------------------
// Catalog (datasets + snippets)
// ---------------------------------------------------------------------------

export interface LabCatalogEntry {
  id: string;
  name: string;
  kind: string;
  namespace?: string | null;
  description?: string | null;
  schema_fields: string[];
  snapshot_id?: string | null;
  row_estimate?: number | null;
  medallion_layer?: string | null;
  tags: string[];
}

export async function listCatalogDatasets(
  options: { q?: string; limit?: number } = {},
): Promise<LabCatalogEntry[]> {
  const qs = new URLSearchParams();
  if (options.q) qs.set("q", options.q);
  if (options.limit) qs.set("limit", String(options.limit));
  const path = qs.toString()
    ? `/lab/catalog/datasets?${qs.toString()}`
    : "/lab/catalog/datasets";
  return apiFetch<LabCatalogEntry[]>(path);
}

export async function listCatalogSnippets(
  workspaceId?: string,
): Promise<LabCatalogEntry[]> {
  const qs = new URLSearchParams();
  if (workspaceId) qs.set("workspace_id", workspaceId);
  const path = qs.toString()
    ? `/lab/catalog/snippets?${qs.toString()}`
    : "/lab/catalog/snippets";
  return apiFetch<LabCatalogEntry[]>(path);
}

// ---------------------------------------------------------------------------
// Notes
// ---------------------------------------------------------------------------

export interface LabNoteCreate {
  lab_id: string;
  target_kind: "graph" | "run" | "node_run" | "label" | "paper_chunk" | "snippet";
  target_id: string;
  body_md: string;
  citations?: Array<Record<string, unknown>>;
}

export interface LabNoteOut {
  id: string;
  lab_id: string;
  target_kind: string;
  target_id: string;
  body_md: string;
  citations: Array<Record<string, unknown>>;
  created_at: string;
}

export async function createLabNote(body: LabNoteCreate): Promise<LabNoteOut> {
  return apiFetch<LabNoteOut>("/lab/notes", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listLabNotes(
  options: {
    labId: string;
    targetKind?: LabNoteCreate["target_kind"];
    targetId?: string;
    limit?: number;
  },
): Promise<LabNoteOut[]> {
  const qs = new URLSearchParams({ lab_id: options.labId });
  if (options.targetKind) qs.set("target_kind", options.targetKind);
  if (options.targetId) qs.set("target_id", options.targetId);
  if (options.limit) qs.set("limit", String(options.limit));
  return apiFetch<LabNoteOut[]>(`/lab/notes?${qs.toString()}`);
}

// ---------------------------------------------------------------------------
// RAG sidecar
// ---------------------------------------------------------------------------

export interface LabRagHit {
  chunk_id: string;
  paper_title?: string | null;
  source_uri?: string | null;
  text: string;
  score: number;
  rank: number;
}

export interface LabRagQueryRequest {
  lab_id: string;
  query: string;
  k?: number;
  tags?: string[];
}

export interface LabRagQueryResponse {
  query: string;
  hits: LabRagHit[];
}

export async function ragQuery(
  body: LabRagQueryRequest,
): Promise<LabRagQueryResponse> {
  return apiFetch<LabRagQueryResponse>("/lab/rag/query", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// EDA cell promotion (Phase 1)
// ---------------------------------------------------------------------------

export interface PromoteCellRequest {
  lab_id: string;
  workspace_id?: string | null;
  source: string;
  cell_label?: string;
  inputs?: Record<string, Record<string, unknown>>;
}

export async function promoteCellToTestingGraph(
  sessionId: string,
  cellId: string,
  body: PromoteCellRequest,
): Promise<LabGraphOut> {
  return apiFetch<LabGraphOut>(
    `/lab/eda/${encodeURIComponent(sessionId)}/cells/${encodeURIComponent(cellId)}/promote`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}
