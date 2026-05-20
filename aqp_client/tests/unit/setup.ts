import "@testing-library/jest-dom/vitest";

/*
 * Polyfill ResizeObserver for Radix primitives + @tanstack/react-virtual
 * running in jsdom. The virtualizer relies on the observer to learn the
 * scroll-element's content size; a no-op observer leaves it at zero and
 * `getVirtualItems()` returns an empty array. We fire the callback once
 * synchronously per `observe()` with a synthesized rect so the
 * virtualizer reports a non-zero viewport.
 */
class ResizeObserverPolyfill {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element): void {
    const rect = target.getBoundingClientRect();
    const entry: ResizeObserverEntry = {
      target,
      contentRect: rect,
      borderBoxSize: [{ inlineSize: rect.width, blockSize: rect.height }],
      contentBoxSize: [{ inlineSize: rect.width, blockSize: rect.height }],
      devicePixelContentBoxSize: [{ inlineSize: rect.width, blockSize: rect.height }],
    };
    queueMicrotask(() => this.callback([entry], this as unknown as ResizeObserver));
  }
  unobserve(): void {}
  disconnect(): void {}
}

if (typeof globalThis.ResizeObserver === "undefined") {
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserverPolyfill }).ResizeObserver =
    ResizeObserverPolyfill;
}

/*
 * `useVirtualizer` (used by ProgressTimeline + DataTable) measures the
 * scroll element via `getBoundingClientRect()` / `clientHeight`. jsdom
 * reports zero by default, which collapses the rendered count to 0
 * and breaks any test that asserts on rendered virtualized rows.
 *
 * We patch the prototype to report a non-zero viewport so
 * `useVirtualizer` renders enough rows for assertions. The runtime
 * behaviour in real browsers is unaffected.
 */
if (!Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")?.get) {
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get() {
      return 600;
    },
  });
}
if (!Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth")?.get) {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get() {
      return 800;
    },
  });
}
if (!Object.getOwnPropertyDescriptor(Element.prototype, "scrollTo")) {
  Object.defineProperty(Element.prototype, "scrollTo", {
    configurable: true,
    writable: true,
    value: () => {},
  });
}

// `useVirtualizer` also reads `getBoundingClientRect()`. jsdom returns
// all zeros — patch it for HTMLElements specifically so layout-aware
// libraries see a sensible viewport.
const originalGetRect = Element.prototype.getBoundingClientRect;
Element.prototype.getBoundingClientRect = function patchedGetRect() {
  const inferredHeight = (this as HTMLElement).clientHeight || 600;
  const inferredWidth = (this as HTMLElement).clientWidth || 800;
  const orig = originalGetRect.call(this);
  if (orig.width === 0 && orig.height === 0) {
    return {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      bottom: inferredHeight,
      right: inferredWidth,
      width: inferredWidth,
      height: inferredHeight,
      toJSON() {
        return {};
      },
    } as DOMRect;
  }
  return orig;
};
