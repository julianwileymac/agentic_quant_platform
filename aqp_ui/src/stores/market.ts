"use client";

import { create } from "zustand";

export interface MarketTick {
  symbol: string;
  ts: number;
  price: number;
  size?: number;
  side?: "buy" | "sell";
}

interface MarketState {
  bySymbol: Record<string, MarketTick[]>;
  pushTick: (tick: MarketTick) => void;
  resetSymbol: (symbol: string) => void;
}

const MAX_TICKS = 2000;

/**
 * Bounded tick ring buffer fed by the rAF batcher in useMarketStream.
 * Per-symbol slice avoids cross-symbol re-renders.
 *
 * Mirrors aqp_client/src/store/market.ts.
 */
export const useMarketStore = create<MarketState>((set) => ({
  bySymbol: {},
  pushTick: (tick) =>
    set((s) => {
      const existing = s.bySymbol[tick.symbol] ?? [];
      const next = [...existing, tick];
      if (next.length > MAX_TICKS) next.splice(0, next.length - MAX_TICKS);
      return { bySymbol: { ...s.bySymbol, [tick.symbol]: next } };
    }),
  resetSymbol: (symbol) =>
    set((s) => {
      const { [symbol]: _removed, ...rest } = s.bySymbol;
      return { bySymbol: rest };
    }),
}));
