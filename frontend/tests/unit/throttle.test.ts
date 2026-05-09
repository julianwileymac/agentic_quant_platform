import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createRafBatcher } from "@/lib/ws/throttle";

describe("createRafBatcher", () => {
  let nowMs = 0;
  let frameCallbacks: FrameRequestCallback[] = [];

  beforeEach(() => {
    nowMs = 0;
    frameCallbacks = [];
    vi.spyOn(globalThis, "requestAnimationFrame").mockImplementation((cb) => {
      frameCallbacks.push(cb);
      return frameCallbacks.length;
    });
    vi.spyOn(globalThis, "cancelAnimationFrame").mockImplementation((id) => {
      frameCallbacks[id - 1] = () => {};
    });
    vi.spyOn(performance, "now").mockImplementation(() => nowMs);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /**
   * Fires every queued frame callback at the supplied wall-clock time.
   */
  function flushFrames(toMs: number): void {
    nowMs = toMs;
    const pending = frameCallbacks;
    frameCallbacks = [];
    for (const cb of pending) cb(toMs);
  }

  it("collapses a 1 kHz tick stream into ~30 batches per second", () => {
    const flush = vi.fn<(batch: number[]) => void>();
    const batcher = createRafBatcher<number>(flush, { fpsCap: 30 });

    // Push 1000 ticks across 1000 ms (one per ms). The batcher only
    // schedules one rAF per push burst; the rAF callback decides
    // whether enough wallclock time has elapsed since the last flush.
    for (let i = 0; i < 1000; i += 1) {
      batcher.push(i);
      // Fire a frame at the current ms wall clock so the batcher has
      // a chance to drain. With fpsCap=30, drains happen at most
      // every 33.33 ms -- earlier frames get rescheduled.
      flushFrames(i + 1);
    }
    // Final force-flush captures any tail messages still queued
    // after the last natural drain window (mirrors how the WS
    // consumer calls flushNow on close).
    batcher.flushNow();

    // Expect ~30 flushes (allow some slack for sub-ms drift). The
    // final force-flush adds one extra batch.
    expect(flush.mock.calls.length).toBeGreaterThanOrEqual(28);
    expect(flush.mock.calls.length).toBeLessThanOrEqual(36);

    // Total messages flushed must equal the number pushed (no drops at this rate).
    const total = flush.mock.calls.reduce((sum, [batch]) => sum + batch.length, 0);
    expect(total).toBe(1000);
    batcher.dispose();
  });

  it("drops the oldest messages when the bounded queue overflows", () => {
    const flush = vi.fn<(batch: number[]) => void>();
    const batcher = createRafBatcher<number>(flush, { fpsCap: 30, maxQueue: 8 });

    // Push 100 messages without ever calling rAF. The queue must cap
    // at the maxQueue ceiling so memory stays bounded.
    for (let i = 0; i < 100; i += 1) batcher.push(i);
    expect(batcher.size()).toBe(8);

    flushFrames(100);
    const batch = flush.mock.calls[0]?.[0];
    expect(batch?.length).toBe(8);
    // The most recent 8 messages (92..99) must survive — recency
    // wins over completeness.
    expect(batch).toEqual([92, 93, 94, 95, 96, 97, 98, 99]);
    batcher.dispose();
  });

  it("forces an immediate drain on flushNow", () => {
    const flush = vi.fn<(batch: number[]) => void>();
    const batcher = createRafBatcher<number>(flush, { fpsCap: 30 });
    batcher.push(1);
    batcher.push(2);
    batcher.flushNow();
    expect(flush).toHaveBeenCalledOnce();
    expect(flush.mock.calls[0]?.[0]).toEqual([1, 2]);
    batcher.dispose();
  });

  it("does nothing after dispose", () => {
    const flush = vi.fn<(batch: number[]) => void>();
    const batcher = createRafBatcher<number>(flush, { fpsCap: 30 });
    batcher.dispose();
    batcher.push(1);
    flushFrames(100);
    expect(flush).not.toHaveBeenCalled();
  });
});
