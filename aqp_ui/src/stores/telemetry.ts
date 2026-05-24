"use client";

import { create } from "zustand";

export interface TelemetryFrame {
  task_id: string;
  stage?: string;
  message?: string;
  timestamp?: number;
  pct?: number;
  [k: string]: unknown;
}

interface TelemetryState {
  byTask: Record<string, TelemetryFrame[]>;
  pushFrame: (frame: TelemetryFrame) => void;
  reset: (taskId: string) => void;
}

const MAX_FRAMES = 5000;

/**
 * Per-task progress ring buffer.
 *
 * AGENTS rule 9: WS frames preserve {task_id, stage, message, timestamp, **extras}.
 * The buffer is bounded to prevent heap blowup on long-running tasks.
 */
export const useTelemetryStore = create<TelemetryState>((set) => ({
  byTask: {},
  pushFrame: (frame) =>
    set((s) => {
      if (!frame.task_id) return s;
      const existing = s.byTask[frame.task_id] ?? [];
      const next = [...existing, frame];
      if (next.length > MAX_FRAMES) {
        next.splice(0, next.length - MAX_FRAMES);
      }
      return { byTask: { ...s.byTask, [frame.task_id]: next } };
    }),
  reset: (taskId) =>
    set((s) => {
      const { [taskId]: _removed, ...rest } = s.byTask;
      return { byTask: rest };
    }),
}));
