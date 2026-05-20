/**
 * API + WebSocket base URLs.
 *
 * In development Vite proxies `/aqp-api` -> FastAPI and `/aqp-ws` -> WS,
 * so cookies and same-origin headers behave the same as in production
 * behind a reverse proxy. Setting VITE_API_URL / VITE_WS_URL is only
 * useful for direct connections (Playwright headless against a remote
 * cluster, etc).
 */
const FALLBACK_API_BASE = "/aqp-api";
const FALLBACK_WS_BASE = "/aqp-ws";

function resolveOrigin(): string {
  if (typeof window === "undefined") return "";
  return window.location.origin;
}

export const API_BASE_URL: string =
  import.meta.env.VITE_API_URL || `${resolveOrigin()}${FALLBACK_API_BASE}`;

export const WS_BASE_URL: string = (() => {
  const explicit = import.meta.env.VITE_WS_URL;
  if (explicit) return explicit;
  const origin = resolveOrigin();
  if (!origin) return FALLBACK_WS_BASE;
  const wsScheme = origin.startsWith("https") ? "wss" : "ws";
  const host = origin.replace(/^https?:\/\//, "");
  return `${wsScheme}://${host}${FALLBACK_WS_BASE}`;
})();

export function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  if (!path.startsWith("/")) path = `/${path}`;
  return `${API_BASE_URL}${path}`;
}

export function wsUrl(path: string): string {
  if (/^wss?:\/\//.test(path)) return path;
  if (!path.startsWith("/")) path = `/${path}`;
  return `${WS_BASE_URL}${path}`;
}
