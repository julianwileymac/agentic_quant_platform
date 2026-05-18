import { useEffect, useRef, useState } from "react";

import { useMarketStore } from "@/store/market";

import { createWsClient } from "./client";
import { createRafBatcher } from "./throttle";
import type { LiveEvent, LiveEventOrError, WsStatus } from "./types";

interface UseLiveStreamOptions {
  /** Channel id returned by `POST /live/subscribe`. */
  channelId: string | null;
  /** FPS cap for the rAF batcher. Defaults to 30 -- the human
   *  perceptual ceiling for "smooth" updates. */
  fpsCap?: number;
}

export interface LiveStreamHandle {
  status: WsStatus;
  /** Optional last-error string from the WS payload. */
  error: string | null;
}

/**
 * Subscribes to the live-market WebSocket and pumps every event
 * through the rAF batcher into the shared `useMarketStore`. Components
 * never read off this hook directly — they read selectors off
 * `useMarketStore` (`useLatestEvent(symbol)` / `useRecentEvents()`)
 * so each row in the order book / position table only re-renders
 * when *that* symbol updates.
 *
 * The blueprint's hardware reference points (~17-28 ns FPGA loops vs.
 * ~16.6 ms / 60 fps browser frame budget) make it physically
 * impossible to render every tick. We batch up to `fpsCap` flushes
 * per second, deliberately dropping older queued ticks if the
 * batcher's bounded queue overflows -- recency wins over completeness.
 */
export function useLiveStream({ channelId, fpsCap = 30 }: UseLiveStreamOptions): LiveStreamHandle {
  const [status, setStatus] = useState<WsStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const applyBatch = useMarketStore((s) => s.applyBatch);
  const reset = useMarketStore((s) => s.reset);
  const errorRef = useRef(setError);
  errorRef.current = setError;

  useEffect(() => {
    if (!channelId) {
      setStatus("idle");
      return;
    }
    reset();
    const batcher = createRafBatcher<LiveEvent>(applyBatch, { fpsCap });
    const client = createWsClient<LiveEventOrError, never>({
      path: `/live/stream/${channelId}`,
      reconnect: true,
      onStatus: setStatus,
      onMessage: (msg) => {
        if (msg && typeof msg === "object" && "error" in msg && typeof msg.error === "string") {
          errorRef.current(msg.error);
          return;
        }
        if (msg && typeof msg === "object" && "kind" in msg) {
          batcher.push(msg as LiveEvent);
        }
      },
    });
    return () => {
      client.close();
      batcher.dispose();
    };
  }, [channelId, fpsCap, applyBatch, reset]);

  return { status, error };
}
