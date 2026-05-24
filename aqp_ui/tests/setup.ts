import "@testing-library/jest-dom/vitest";

// Mock window.matchMedia for AntdProvider's prefers-color-scheme check.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Polyfill fetch in jsdom if not present (Vitest 2 ships with a global fetch).
if (typeof globalThis.fetch === "undefined") {
  globalThis.fetch = (() =>
    Promise.reject(new Error("fetch is not mocked"))) as typeof fetch;
}
