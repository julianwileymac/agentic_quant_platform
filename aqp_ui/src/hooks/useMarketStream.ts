"use client";

import { useEffect, useRef, useState } from "react";

import { useMarketStore, type MarketTick } from "@/stores/market";
import type { WsStatus } from "./useCeleryTask";

const FPS_CAP = 30;
const MIN_FRAME_MS = 1000 / FPS_CAP;

/**
 * Subscribe to a live market data channel.
 *
 * rAF-batched at 30 FPS — matches aqp_client/src/lib/ws/useLiveStream.ts.
 * Bounded ring buffer in useMarketStore prevents heap blowup.
 */
export function useMarketStream(symbol: string | null): { status: WsStatus } {
  const pushTick = useMarketStore((s) => s.pushTick);
  const [status, setStatus] = useState<WsStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const queueRef = useRef<MarketTick[]>([]);
  const rafRef = useRef<number | null>(null);
  const lastFrameRef = useRef(0);
  const attemptRef = useRef(0);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (!symbol) return;
    cancelledRef.current = false;

    const flush = (now: number) => {
      rafRef.current = null;
      if (now - lastFrameRef.current < MIN_FRAME_MS) {
        rafRef.current = requestAnimationFrame(flush);
        return;
      }
      lastFrameRef.current = now;
      const batch = queueRef.current.splice(0);
      for (const tick of batch) pushTick(tick);
      if (queueRef.current.length > 0) {
        rafRef.current = requestAnimationFrame(flush);
      }
    };

    const schedule = () => {
      if (rafRef.current != null) return;
      rafRef.current = requestAnimationFrame(flush);
    };

    const connect = async () => {
      if (cancelledRef.current) return;
      setStatus("connecting");
      try {
        const ticketRes = await fetch(
          `/api/ws-token?channelId=live%3A${encodeURIComponent(symbol)}`,
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
            const tick = JSON.parse(ev.data) as MarketTick;
            queueRef.current.push(tick);
            schedule();
          } catch {
            // ignore malformed
          }
        };
        ws.onerror = () => setStatus("error");
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
      }
    };

    connect();

    return () => {
      cancelledRef.current = true;
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      wsRef.current?.close();
    };
  }, [symbol, pushTick]);

  return { status };
}
