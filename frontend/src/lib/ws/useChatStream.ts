import { useCallback, useEffect, useRef, useState } from "react";

import { createWsClient } from "./client";
import type { ProgressEvent, WsStatus } from "./types";

const TERMINAL = new Set(["done", "error"]);

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

  const reset = useCallback(() => {
    setEvents([]);
    setText("");
    setDone(false);
    setError(null);
    setStatus("idle");
  }, []);

  useEffect(() => {
    reset();
    if (!taskId) return;
    const path =
      channel === "chat"
        ? `/chat/stream/${taskId}`
        : channel === "assistants"
          ? `/assistants/stream/${taskId}`
          : channel === "terraform"
            ? `/ws/terraform/runs/${taskId}`
            : `/agents/runs/${taskId}/stream`;
    const client = createWsClient<ProgressEvent, never>({
      path,
      reconnect: false,
      onStatus: setStatus,
      onMessage: (msg) => {
        setEvents((prev) => [...prev, msg]);
        if (typeof msg.delta === "string") {
          setText((t) => t + msg.delta);
        } else if (msg.stage === "done" && typeof msg.content === "string") {
          setText(msg.content);
        }
        if (msg.stage === "error") {
          setError(typeof msg.error === "string" ? msg.error : (msg.message ?? "stream error"));
        }
        if (msg.stage && TERMINAL.has(String(msg.stage))) {
          setDone(true);
        }
      },
      isTerminal: (m) => Boolean(m.stage && TERMINAL.has(String(m.stage))),
    });
    return () => client.close();
  }, [taskId, channel, reset]);

  return { status, events, text, done, error, reset };
}
