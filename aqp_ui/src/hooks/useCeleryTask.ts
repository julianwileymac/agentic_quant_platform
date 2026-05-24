"use client";

import { useEffect, useRef, useState } from "react";

import { useTelemetryStore, type TelemetryFrame } from "@/stores/telemetry";

export type WsStatus = "idle" | "connecting" | "open" | "closed" | "error";

/**
 * Subscribe to a Celery task's progress stream via WSS.
 *
 * Frame contract (AGENTS rule 9):
 *   {task_id, stage, message, timestamp, **extras}
 *
 * Flow:
 *   1. Mint a short-lived ticket via /api/ws-token?taskId=...
 *   2. Open WSS using the returned URL.
 *   3. Push every frame into useTelemetryStore for the matching task.
 *   4. Reconnect on close with exponential backoff (500ms -> 30s).
 *
 * Mirrors aqp_client/src/lib/ws/useChatStream.ts.
 */
export function useCeleryTask(taskId: string | null): { status: WsStatus } {
  const pushFrame = useTelemetryStore((s) => s.pushFrame);
  const [status, setStatus] = useState<WsStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (!taskId) return;
    cancelledRef.current = false;

    const connect = async () => {
      if (cancelledRef.current) return;
      setStatus("connecting");
      try {
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
  }, [taskId, pushFrame]);

  return { status };
}
