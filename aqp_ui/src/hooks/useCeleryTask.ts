"use client";

import { useEffect, useRef, useState } from "react";

import { useTelemetryStore, type TelemetryFrame } from "@/stores/telemetry";

export type WsStatus = "idle" | "connecting" | "open" | "closed" | "error";

interface ReplayResponse {
  task_id: string;
  since: string | null;
  frames: TelemetryFrame[];
  last_frame_id: string | null;
}

/**
 * Subscribe to a Celery task's progress stream via WSS.
 *
 * Frame contract (AGENTS rule 4):
 *   {task_id, stage, message, timestamp, **extras}
 *
 * Flow:
 *   1. Mint a short-lived ticket via /api/ws-token?taskId=...
 *   2. (Phase 3 cloud-dash refactor) If this is a reconnect AND the
 *      telemetry store has a `lastFrameId` for this task, fetch
 *      `/api/chat/replay/{taskId}?since={lastFrameId}` first so the
 *      UI sees every frame that landed during the disconnect window.
 *   3. Open WSS using the returned URL.
 *   4. Push every frame into useTelemetryStore for the matching task.
 *   5. Reconnect on close with exponential backoff (500ms -> 30s).
 *
 * Mirrors aqp_client/src/lib/ws/useChatStream.ts.
 */
export function useCeleryTask(taskId: string | null): { status: WsStatus } {
  const pushFrame = useTelemetryStore((s) => s.pushFrame);
  const getLastFrameId = useTelemetryStore((s) => s.getLastFrameId);
  const [status, setStatus] = useState<WsStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (!taskId) return;
    cancelledRef.current = false;

    const replayMissedFrames = async (): Promise<void> => {
      const since = getLastFrameId(taskId);
      try {
        const url = since
          ? `/api/chat/replay/${encodeURIComponent(taskId)}?since=${encodeURIComponent(since)}`
          : `/api/chat/replay/${encodeURIComponent(taskId)}`;
        const res = await fetch(url, { credentials: "include" });
        if (!res.ok) return;
        const body = (await res.json()) as ReplayResponse;
        for (const frame of body.frames ?? []) {
          if (!cancelledRef.current) {
            pushFrame(frame);
          }
        }
      } catch {
        // Replay is best-effort — the live socket may still recover
        // older frames if the server keeps a slow consumer hot.
      }
    };

    const connect = async () => {
      if (cancelledRef.current) return;
      setStatus("connecting");
      try {
        // Phase 3 replay: if this is a reconnect attempt, fill the
        // gap from the last frame we saw BEFORE re-opening the live
        // socket so the visual order remains chronological.
        if (attemptRef.current > 0) {
          await replayMissedFrames();
        }
        const ticketRes = await fetch(
          `/api/ws-token?taskId=${encodeURIComponent(taskId)}`,
          { credentials: "include" },
        );
        if (!ticketRes.ok) throw new Error(`ticket ${ticketRes.status}`);
        const { wsUrl } = (await ticketRes.json()) as { wsUrl: string };

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          attemptRef.current = 0;
          setStatus("open");
        };
        ws.onmessage = (ev) => {
          try {
            const frame = JSON.parse(ev.data) as TelemetryFrame;
            pushFrame(frame);
          } catch {
            // ignore malformed frames
          }
        };
        ws.onerror = () => {
          setStatus("error");
        };
        ws.onclose = () => {
          setStatus("closed");
          if (cancelledRef.current) return;
          const delay =
            Math.min(30_000, 500 * 2 ** attemptRef.current) + Math.random() * 250;
          attemptRef.current += 1;
          setTimeout(connect, delay);
        };
      } catch {
        setStatus("error");
        if (cancelledRef.current) return;
        const delay =
          Math.min(30_000, 500 * 2 ** attemptRef.current) + Math.random() * 250;
        attemptRef.current += 1;
        setTimeout(connect, delay);
      }
    };

    connect();

    return () => {
      cancelledRef.current = true;
      wsRef.current?.close();
    };
  }, [taskId, pushFrame, getLastFrameId]);

  return { status };
}
