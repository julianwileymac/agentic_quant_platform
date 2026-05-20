/**
 * Animation-frame batcher.
 *
 * The blueprint mandates that microsecond-level WebSocket traffic is
 * collapsed into batches of at most ~30 FPS before crossing the React
 * render boundary so the reconciler is never overwhelmed. Hardware
 * exchange feeds run at nanosecond cadence (~17-28 ns); the human
 * perceptual ceiling for "live" updates is ~30 fps.
 *
 * The batcher captures incoming messages into an in-memory queue and
 * drains it once per `requestAnimationFrame` tick, but no more
 * frequently than `1000 / fpsCap` ms. When the tab is hidden the
 * browser pauses rAF -- we fall back to setTimeout-driven flush so
 * background WS traffic still drains and the queue never grows
 * without bound.
 */

export interface RafBatcher<T> {
  /** Enqueue a single message; flushed on the next eligible frame. */
  push: (msg: T) => void;
  /** Force-drain the queue immediately (used on stream close). */
  flushNow: () => void;
  /** Tear down the batcher; cancels any pending rAF / timeout. */
  dispose: () => void;
  /** Current queue length, mainly for instrumentation. */
  size: () => number;
}

interface RafBatcherOptions {
  /** Maximum frames per second the consumer wants to render. */
  fpsCap?: number;
  /**
   * Hard ceiling on queue depth. Older messages are dropped FIFO when
   * the queue exceeds this size — we choose recency over completeness
   * because stale price ticks have no value to a trader.
   */
  maxQueue?: number;
  /** Fallback poll interval when the tab is hidden / rAF is paused. */
  hiddenPollMs?: number;
}

const DEFAULT_FPS = 30;
const DEFAULT_MAX_QUEUE = 4_096;
const DEFAULT_HIDDEN_POLL = 250;

const isBrowser =
  typeof globalThis !== "undefined" && typeof globalThis.requestAnimationFrame === "function";

export function createRafBatcher<T>(
  flush: (batch: T[]) => void,
  opts: RafBatcherOptions = {},
): RafBatcher<T> {
  const fpsCap = opts.fpsCap ?? DEFAULT_FPS;
  const minIntervalMs = 1000 / fpsCap;
  const maxQueue = opts.maxQueue ?? DEFAULT_MAX_QUEUE;
  const hiddenPollMs = opts.hiddenPollMs ?? DEFAULT_HIDDEN_POLL;

  let queue: T[] = [];
  let lastFlush = 0;
  let rafHandle: number | null = null;
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;

  const drain = (force = false) => {
    rafHandle = null;
    timeoutHandle = null;
    if (disposed) return;
    if (queue.length === 0) return;
    const now =
      typeof performance !== "undefined" && typeof performance.now === "function"
        ? performance.now()
        : Date.now();
    if (!force && now - lastFlush < minIntervalMs) {
      schedule();
      return;
    }
    const batch = queue;
    queue = [];
    lastFlush = now;
    try {
      flush(batch);
    } catch (err) {
      // Surface but never let an exception in the consumer freeze
      // the batcher; subsequent batches must still drain.
      // eslint-disable-next-line no-console
      console.error("[ws/throttle] flush failed", err);
    }
  };

  /*
   * Wrapper that swallows the timestamp / hidden-poll args so the
   * `force` parameter on `drain` is never accidentally bound to a
   * truthy value by requestAnimationFrame / setTimeout.
   */
  const drainScheduled = () => {
    drain(false);
  };

  const schedule = () => {
    if (disposed) return;
    if (rafHandle != null || timeoutHandle != null) return;
    if (
      isBrowser &&
      (typeof document === "undefined" || document.visibilityState !== "hidden")
    ) {
      rafHandle = globalThis.requestAnimationFrame(drainScheduled);
    } else {
      timeoutHandle = setTimeout(drainScheduled, hiddenPollMs);
    }
  };

  return {
    push(msg) {
      if (disposed) return;
      queue.push(msg);
      if (queue.length > maxQueue) {
        queue.splice(0, queue.length - maxQueue);
      }
      schedule();
    },
    flushNow() {
      if (rafHandle != null) {
        globalThis.cancelAnimationFrame(rafHandle);
        rafHandle = null;
      }
      if (timeoutHandle != null) {
        clearTimeout(timeoutHandle);
        timeoutHandle = null;
      }
      drain(true);
    },
    dispose() {
      disposed = true;
      queue = [];
      if (rafHandle != null) {
        globalThis.cancelAnimationFrame(rafHandle);
        rafHandle = null;
      }
      if (timeoutHandle != null) {
        clearTimeout(timeoutHandle);
        timeoutHandle = null;
      }
    },
    size() {
      return queue.length;
    },
  };
}
