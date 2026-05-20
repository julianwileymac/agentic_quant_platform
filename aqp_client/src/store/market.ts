import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { useShallow } from "zustand/react/shallow";

import type { LiveBar, LiveQuote, LiveSignal, LiveTick } from "@/lib/ws/types";

export type LiveEvent = LiveBar | LiveQuote | LiveTick | LiveSignal;

interface MarketState {
  /** Most-recent event keyed by `vt_symbol`. Subscribers select a
   *  single symbol and only re-render when *that* symbol updates. */
  latestBySymbol: Record<string, LiveEvent>;
  /** Bounded ring buffer of the most recent N events across all
   *  symbols. Used by the live signal log and the order tape. */
  buffer: LiveEvent[];
  /** Last batch wallclock (ms since epoch) for FPS instrumentation. */
  lastBatchAt: number;
  /** Apply a batch of events. Designed to be called from the rAF
   *  batcher so React reconciliation runs at most once per frame. */
  applyBatch: (events: LiveEvent[]) => void;
  /** Reset both the latest map and the ring buffer (call on
   *  workspace switch). */
  reset: () => void;
}

const DEFAULT_BUFFER = 1024;

/**
 * `subscribeWithSelector` middleware enables imperative subscriptions
 * with selector + equality semantics so the OhlcChart can listen for
 * a single-symbol slice without going through React reconciliation.
 */
export const useMarketStore = create<MarketState>()(
  subscribeWithSelector((set) => ({
    latestBySymbol: {},
    buffer: [],
    lastBatchAt: 0,
    applyBatch: (events) =>
      set((prev) => {
        if (!events.length) return prev;
        const nextLatest = { ...prev.latestBySymbol };
        for (const event of events) {
          const symbol = event.vt_symbol;
          if (typeof symbol === "string") {
            nextLatest[symbol] = event;
          }
        }
        const nextBuffer = prev.buffer.concat(events);
        if (nextBuffer.length > DEFAULT_BUFFER) {
          nextBuffer.splice(0, nextBuffer.length - DEFAULT_BUFFER);
        }
        return {
          latestBySymbol: nextLatest,
          buffer: nextBuffer,
          lastBatchAt: Date.now(),
        };
      }),
    reset: () =>
      set({
        latestBySymbol: {},
        buffer: [],
        lastBatchAt: 0,
      }),
  })),
);

/**
 * Subscribe to the most-recent tick / bar / quote for a single symbol.
 * Components that mount this hook only re-render when *their* symbol
 * has a new event — neighbouring rows in the order book never reflow.
 */
export function useLatestEvent(symbol: string | null | undefined): LiveEvent | undefined {
  return useMarketStore((s) => (symbol ? s.latestBySymbol[symbol] : undefined));
}

/**
 * Subscribe to the most-recent N events. Uses `useShallow` so we don't
 * re-render when the underlying buffer reference changes if no events
 * passed our slice criterion.
 */
export function useRecentEvents(limit = 64): LiveEvent[] {
  return useMarketStore(
    useShallow((s) => s.buffer.slice(Math.max(0, s.buffer.length - limit))),
  );
}
