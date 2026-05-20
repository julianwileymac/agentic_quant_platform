import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useMarketStore } from "@/store/market";
import type { LiveBar, LiveTick } from "@/lib/ws/types";

describe("useMarketStore", () => {
  beforeEach(() => {
    useMarketStore.getState().reset();
  });
  afterEach(() => {
    useMarketStore.getState().reset();
  });

  it("indexes events by vt_symbol and bounds the buffer", () => {
    const events: LiveTick[] = Array.from({ length: 1500 }, (_, i) => ({
      kind: "tick",
      timestamp: new Date(1_700_000_000_000 + i * 100).toISOString(),
      vt_symbol: i % 2 === 0 ? "AAPL.NASDAQ" : "MSFT.NASDAQ",
      bid: 100 + i * 0.001,
      ask: 100 + i * 0.001 + 0.05,
      last: 100 + i * 0.001 + 0.025,
      volume: 1,
    }));
    useMarketStore.getState().applyBatch(events);
    const state = useMarketStore.getState();
    // Latest map keyed by symbol.
    expect(state.latestBySymbol["AAPL.NASDAQ"]).toBeDefined();
    expect(state.latestBySymbol["MSFT.NASDAQ"]).toBeDefined();
    // Bounded ring buffer at 1024.
    expect(state.buffer.length).toBe(1024);
    // Most recent event survives at the tail.
    expect(state.buffer[state.buffer.length - 1]?.vt_symbol).toBe("MSFT.NASDAQ");
  });

  it("preserves bars alongside ticks for the same symbol (latest wins)", () => {
    const tick: LiveTick = {
      kind: "tick",
      timestamp: "2026-05-08T20:00:00Z",
      vt_symbol: "AAPL.NASDAQ",
      bid: 100,
      ask: 100.1,
      last: 100.05,
      volume: 1,
    };
    const bar: LiveBar = {
      kind: "bar",
      timestamp: "2026-05-08T20:00:01Z",
      vt_symbol: "AAPL.NASDAQ",
      open: 100,
      high: 101,
      low: 99,
      close: 100.5,
      volume: 5_000,
    };
    useMarketStore.getState().applyBatch([tick]);
    expect(useMarketStore.getState().latestBySymbol["AAPL.NASDAQ"]).toMatchObject({ kind: "tick" });
    useMarketStore.getState().applyBatch([bar]);
    expect(useMarketStore.getState().latestBySymbol["AAPL.NASDAQ"]).toMatchObject({ kind: "bar" });
  });
});
