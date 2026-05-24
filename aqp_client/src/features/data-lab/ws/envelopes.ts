/**
 * Typed Lab WebSocket envelopes — mirror the server-side projection
 * in `aqp/lab/ws/protocol.py` so the React Flow consumer can switch
 * on `kind` instead of regex-matching `stage` strings.
 *
 * Every envelope extends the canonical `{task_id, stage, message,
 * timestamp, **extras}` frame shape (AGENTS rule 4). We never rename
 * the top-level keys — only add typed extras keyed by `kind`.
 */

export type LabEnvelopeKind =
  | "run.status"
  | "run.metric"
  | "run.log"
  | "run.partial"
  | "run.artifact"
  | "eda.cell.result"
  | "sim.tick"
  | "stream.market";

export interface LabEnvelopeBase {
  v: number;
  kind: LabEnvelopeKind;
  task_id: string;
  timestamp: number;
  stage: string;
  message: string;
  tags?: Record<string, string>;
  context?: Record<string, string>;
}

export interface RunStatusEnvelope extends LabEnvelopeBase {
  kind: "run.status";
  run_id: string;
  node_id?: string | null;
  state: "queued" | "running" | "done" | "error" | "halted" | "cancelled";
  content_hash?: string | null;
}

export interface RunMetricEnvelope extends LabEnvelopeBase {
  kind: "run.metric";
  run_id: string;
  node_id: string;
  name: string;
  value: unknown;
}

export interface RunLogEnvelope extends LabEnvelopeBase {
  kind: "run.log";
  run_id: string;
  node_id?: string | null;
  level: "debug" | "info" | "warning" | "error";
  msg: string;
}

export interface RunPartialEnvelope extends LabEnvelopeBase {
  kind: "run.partial";
  run_id: string;
  node_id: string;
  schema: string;
  rows: Array<Array<unknown>>;
}

export interface RunArtifactEnvelope extends LabEnvelopeBase {
  kind: "run.artifact";
  run_id: string;
  node_id: string;
  uri: string;
  artifact_kind: string;
  schema?: Record<string, unknown> | null;
}

export interface EdaCellResultEnvelope extends LabEnvelopeBase {
  kind: "eda.cell.result";
  cell_id: string;
  stale_ids: string[];
  render: Record<string, unknown>;
  /** Optional execution status surfaced by the EdaKernel; `done` or `error`. */
  status?: "done" | "error" | "running" | "pending";
  /** Optional captured stdout / stderr / error string. */
  stdout?: string;
  stderr?: string;
  error?: string | null;
  repr?: string | null;
  duration_ms?: number;
}

export interface SimTickEnvelope extends LabEnvelopeBase {
  kind: "sim.tick";
  run_id: string;
  t_ns: number;
  lob?: Record<string, unknown> | null;
  pnl?: number | null;
  pos?: number | null;
  signals?: Record<string, unknown> | null;
}

export interface StreamMarketEnvelope extends LabEnvelopeBase {
  kind: "stream.market";
  topic: string;
  payload: Record<string, unknown>;
}

export type LabServerEnvelope =
  | RunStatusEnvelope
  | RunMetricEnvelope
  | RunLogEnvelope
  | RunPartialEnvelope
  | RunArtifactEnvelope
  | EdaCellResultEnvelope
  | SimTickEnvelope
  | StreamMarketEnvelope;

// ---------------------------------------------------------------------------
// Client-side envelopes
// ---------------------------------------------------------------------------

export interface SubscribeEnvelope {
  v?: number;
  kind: "subscribe";
  stream: "run" | "live";
  id: string;
}

export interface UnsubscribeEnvelope {
  v?: number;
  kind: "unsubscribe";
  stream: "run" | "live";
  id: string;
}

export interface EdaExecEnvelope {
  v?: number;
  kind: "eda.exec";
  cell_id: string;
  code: string;
}

export interface SimCommandEnvelope {
  v?: number;
  kind: "sim.command";
  run_id: string;
  cmd: "pause" | "resume" | "step" | "seed" | "speed";
  value?: unknown;
}

export type LabClientEnvelope =
  | SubscribeEnvelope
  | UnsubscribeEnvelope
  | EdaExecEnvelope
  | SimCommandEnvelope;

export function isLabServerEnvelope(
  value: unknown,
): value is LabServerEnvelope {
  if (!value || typeof value !== "object") return false;
  const env = value as { kind?: unknown };
  return typeof env.kind === "string";
}
