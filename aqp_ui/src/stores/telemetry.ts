"use client";

import { create } from "zustand";

export interface TelemetryFrame {
  task_id: string;
  stage?: string;
  message?: string;
  timestamp?: number;
  pct?: number;
  /**
   * Redis-Stream id assigned by the backend replay buffer
   * (`aqp:task:frames:<task_id>`). Used by
   * [`useCeleryTask`](../hooks/useCeleryTask.ts) to resume after a
   * reconnect. Live frames published before Phase 3 backfill may
   * not carry this field; treat absence as "no replay anchor".
   */
  frame_id?: string;
  [k: string]: unknown;
}

interface TelemetryState {
  /** Per-task ring buffer of frames (bounded by `MAX_FRAMES`). */
  byTask: Record<string, TelemetryFrame[]>;
  /** Per-task last-seen Redis-Stream id; persists across reloads. */
  lastFrameByTask: Record<string, string | undefined>;
  pushFrame: (frame: TelemetryFrame) => void;
  reset: (taskId: string) => void;
  getLastFrameId: (taskId: string) => string | undefined;
}

const MAX_FRAMES = 5000;
const STORAGE_KEY = "aqp-ui-telemetry-last-frame";
const STORAGE_TTL_MS = 5 * 60 * 1000;

interface PersistedShape {
  ts: number;
  byTask: Record<string, string>;
}

function loadPersisted(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as PersistedShape;
    if (Date.now() - parsed.ts > STORAGE_TTL_MS) return {};
    return parsed.byTask ?? {};
  } catch {
    return {};
  }
}

function savePersisted(byTask: Record<string, string | undefined>): void {
  if (typeof window === "undefined") return;
  try {
    const filtered: Record<string, string> = {};
    for (const [taskId, frameId] of Object.entries(byTask)) {
      if (typeof frameId === "string" && frameId.length > 0) {
        filtered[taskId] = frameId;
      }
    }
    const body: PersistedShape = { ts: Date.now(), byTask: filtered };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(body));
  } catch {
    // localStorage unavailable / quota exceeded — drop silently.
  }
}

/**
 * Per-task progress ring buffer with replay-anchor persistence.
 *
 * AGENTS rule 4: frame shape `{task_id, stage, message, timestamp,
 * **extras}` is preserved — `frame_id` is an extra, not a rename.
 * Buffer bounded to prevent heap blowup on long-running tasks.
 *
 * Phase 3 of the cloud-dash refactor: `lastFrameByTask` is hydrated
 * from `localStorage` on first construction and persisted on every
 * `pushFrame` so a tab refresh during a live backtest doesn't lose
 * the resume anchor.
 */
export const useTelemetryStore = create<TelemetryState>((set, get) => ({
  byTask: {},
  lastFrameByTask: loadPersisted(),
  pushFrame: (frame) =>
    set((s) => {
      if (!frame.task_id) return s;
      const existing = s.byTask[frame.task_id] ?? [];
      const next = [...existing, frame];
      if (next.length > MAX_FRAMES) {
        next.splice(0, next.length - MAX_FRAMES);
      }
      const updatedLast: Record<string, string | undefined> = {
        ...s.lastFrameByTask,
      };
      if (typeof frame.frame_id === "string" && frame.frame_id.length > 0) {
        updatedLast[frame.task_id] = frame.frame_id;
      }
      savePersisted(updatedLast);
      return {
        byTask: { ...s.byTask, [frame.task_id]: next },
        lastFrameByTask: updatedLast,
      };
    }),
  reset: (taskId) =>
    set((s) => {
      const { [taskId]: _frames, ...restFrames } = s.byTask;
      const { [taskId]: _last, ...restLast } = s.lastFrameByTask;
      savePersisted(restLast);
      return { byTask: restFrames, lastFrameByTask: restLast };
    }),
  getLastFrameId: (taskId) => get().lastFrameByTask[taskId],
}));
