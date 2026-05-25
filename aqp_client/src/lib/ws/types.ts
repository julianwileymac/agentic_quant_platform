/**
 * Live market events as published by FastAPI on `/live/stream/{channel}`.
 * Mirrors the contract in `aqp.api.routes.live` exactly so we never
 * desynchronise the client / server payload shape.
 */
export interface LiveBar {
  kind: "bar";
  timestamp: string;
  vt_symbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LiveQuote {
  kind: "quote";
  timestamp: string;
  vt_symbol: string;
  bid_close: number;
  ask_close: number;
  bid_size: number;
  ask_size: number;
}

export interface LiveTick {
  kind: "tick";
  timestamp: string;
  vt_symbol: string | null;
  bid: number;
  ask: number;
  last: number;
  volume: number;
}

export interface LiveSignal {
  kind: "signal";
  timestamp: string;
  vt_symbol: string | null;
  strength: number;
  direction: string;
  confidence: number;
  source: string;
}

export type LiveEvent = LiveBar | LiveQuote | LiveTick | LiveSignal;
export type LiveEventOrError = LiveEvent | { error: string };

/**
 * Celery / agent progress event published by `aqp.tasks._progress.emit`
 * over Redis and relayed to the browser via `/chat/stream/{task_id}`
 * and `/agents/runs/{run_id}/stream`. The required shape is
 * `{task_id, stage, message, timestamp, **extras}` (AGENTS.md rule 4)
 * — extending is fine; renaming keys is not.
 *
 * Phase 3 (WS replay) of the cloud-dash refactor adds an optional
 * `frame_id` field — the Redis-Stream id assigned by the backend
 * replay buffer (`aqp:task:frames:<task_id>`). Clients persist the
 * last seen `frame_id` and pass it to `/chat/replay/{task_id}?since=`
 * on reconnect to recover frames that landed during a disconnect.
 */
export interface ProgressEvent {
  task_id?: string;
  stage?: "starting" | "running" | "tool" | "thinking" | "done" | "error" | string;
  message?: string;
  timestamp?: string;
  /** Redis-Stream id; only populated for frames that went through
   *  the Phase 3 replay-buffered emit path. */
  frame_id?: string;
  agent?: string;
  tool?: string;
  tool_input?: unknown;
  tool_output?: unknown;
  delta?: string;
  content?: string;
  data?: unknown;
  error?: string;
  [extra: string]: unknown;
}

/**
 * Shape of the `/chat/replay/{task_id}` response used by
 * `useChatStream`'s reconnect hook.
 */
export interface ReplayResponse {
  task_id: string;
  since: string | null;
  frames: ProgressEvent[];
  last_frame_id: string | null;
}

/** WebSocket connection state surfaced to consumers. */
export type WsStatus = "idle" | "connecting" | "open" | "closed" | "error";
