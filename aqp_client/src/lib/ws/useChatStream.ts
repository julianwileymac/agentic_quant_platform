import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api/client";

import { createWsClient } from "./client";
import type { ProgressEvent, ReplayResponse, WsStatus } from "./types";

const TERMINAL = new Set(["done", "error"]);

const REPLAY_STORAGE_KEY = "aqp-client-ws-last-frame";
const REPLAY_STORAGE_TTL_MS = 5 * 60 * 1000;

interface PersistedReplayShape {
  ts: number;
  byTask: Record<string, string>;
}

function loadLastFrameId(taskId: string): string | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const raw = window.localStorage.getItem(REPLAY_STORAGE_KEY);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as PersistedReplayShape;
    if (Date.now() - parsed.ts > REPLAY_STORAGE_TTL_MS) return undefined;
    return parsed.byTask?.[taskId];
  } catch {
    return undefined;
  }
}

function saveLastFrameId(taskId: string, frameId: string | undefined): void {
  if (typeof window === "undefined" || !frameId) return;
  try {
    const raw = window.localStorage.getItem(REPLAY_STORAGE_KEY);
    const existing = raw ? (JSON.parse(raw) as PersistedReplayShape) : null;
    const stale = existing && Date.now() - existing.ts > REPLAY_STORAGE_TTL_MS;
    const byTask = stale ? {} : (existing?.byTask ?? {});
    byTask[taskId] = frameId;
    window.localStorage.setItem(
      REPLAY_STORAGE_KEY,
      JSON.stringify({ ts: Date.now(), byTask } satisfies PersistedReplayShape),
    );
  } catch {
    // localStorage quota / unavailable — drop silently.
  }
}

export interface ChatStreamState {
  status: WsStatus;
  events: ProgressEvent[];
  /** Concatenated assistant `delta` / `content` chunks. */
  text: string;
  done: boolean;
  error: string | null;
  reset: () => void;
}

/**
 * Subscribes to a Celery / Agent progress stream. Preserves the
 * required `{task_id, stage, message, timestamp, **extras}` payload
 * shape end-to-end (AGENTS.md rule 4) -- we never rename, only narrow
 * for typed access. Used by the assistant drawer, agent run detail,
 * crew trace, backtest progress, and ML training pages.
 *
 * Phase 3 (WS replay) of the cloud-dash refactor:
 *
 * - We persist the last seen `frame_id` to localStorage (TTL 5min)
 *   so a tab refresh during a live backtest doesn't lose the resume
 *   anchor.
 * - On every reconnect the client first calls `/chat/replay/{taskId}`
 *   with `?since={lastFrameId}` and synthesises the missed frames
 *   through `onMessage` BEFORE the live socket re-opens, so the
 *   visual frame order remains chronological.
 * - Reconnect is now enabled by default for the chat / agents /
 *   assistants channels so the replay machinery actually fires; the
 *   terraform channel keeps `reconnect: false` because its server
 *   end auto-streams and reconnect semantics differ.
 */
export function useChatStream(
  taskId: string | null,
  channel: "chat" | "agents" | "assistants" | "terraform" = "chat",
): ChatStreamState {
  const [status, setStatus] = useState<WsStatus>("idle");
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [text, setText] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventsRef = useRef<ProgressEvent[]>([]);
  eventsRef.current = events;
  const lastFrameRef = useRef<string | undefined>(undefined);

  const reset = useCallback(() => {
    setEvents([]);
    setText("");
    setDone(false);
    setError(null);
    setStatus("idle");
    lastFrameRef.current = undefined;
  }, []);

  useEffect(() => {
    reset();
    if (!taskId) return;
    lastFrameRef.current = loadLastFrameId(taskId);
    const path =
      channel === "chat"
        ? `/chat/stream/${taskId}`
        : channel === "assistants"
          ? `/assistants/stream/${taskId}`
          : channel === "terraform"
            ? `/ws/terraform/runs/${taskId}`
            : `/agents/runs/${taskId}/stream`;
    const handleFrame = (msg: ProgressEvent): void => {
      setEvents((prev) => [...prev, msg]);
      if (typeof msg.delta === "string") {
        setText((t) => t + msg.delta);
      } else if (msg.stage === "done" && typeof msg.content === "string") {
        setText(msg.content);
      }
      if (msg.stage === "error") {
        setError(
          typeof msg.error === "string" ? msg.error : (msg.message ?? "stream error"),
        );
      }
      if (msg.stage && TERMINAL.has(String(msg.stage))) {
        setDone(true);
      }
      if (typeof msg.frame_id === "string" && msg.frame_id.length > 0) {
        lastFrameRef.current = msg.frame_id;
        saveLastFrameId(taskId, msg.frame_id);
      }
    };
    const replayMissedFrames = async (): Promise<void> => {
      // Replay only applies to the chat / agents / assistants
      // channels — terraform has its own stream contract.
      if (channel === "terraform") return;
      try {
        const since = lastFrameRef.current;
        const body = await apiFetch<ReplayResponse>(
          `/chat/replay/${encodeURIComponent(taskId)}`,
          {
            query: since ? { since, limit: 500 } : { limit: 500 },
          },
        );
        for (const frame of body.frames ?? []) {
          handleFrame(frame);
        }
      } catch {
        // Best-effort — the live socket may still recover frames.
      }
    };

    const client = createWsClient<ProgressEvent, never>({
      path,
      reconnect: channel !== "terraform",
      onStatus: setStatus,
      onMessage: handleFrame,
      beforeReconnect: replayMissedFrames,
      isTerminal: (m) => Boolean(m.stage && TERMINAL.has(String(m.stage))),
    });
    return () => client.close();
  }, [taskId, channel, reset]);

  return { status, events, text, done, error, reset };
}
