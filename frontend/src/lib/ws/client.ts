import { wsUrl } from "@/lib/api/config";
import { getTenancyHeaders } from "@/store/tenancy";

import type { WsStatus } from "./types";

export interface WsClientOptions<TIn> {
  /** Path or absolute ws URL. Path is resolved through `WS_BASE_URL`. */
  path: string;
  /** Called once for every incoming JSON-decoded message. */
  onMessage: (msg: TIn) => void;
  /** Called when the underlying connection state changes. */
  onStatus?: (status: WsStatus) => void;
  /** Optional message → boolean predicate; returning true closes the loop. */
  isTerminal?: (msg: TIn) => boolean;
  /** Reconnect on close/error. Defaults to true. */
  reconnect?: boolean;
  /** Initial reconnect delay (exponential backoff up to `maxBackoffMs`). */
  backoffMs?: number;
  maxBackoffMs?: number;
  /** Optional heartbeat ping payload sent every `intervalMs`. */
  heartbeat?: { intervalMs: number; payload: unknown };
}

export interface WsClient<TOut> {
  status: () => WsStatus;
  send: (msg: TOut) => void;
  close: () => void;
  reopen: () => void;
}

const DEFAULT_BACKOFF = 500;
const DEFAULT_MAX_BACKOFF = 8_000;

/**
 * Plain-vanilla WebSocket factory with reconnect, heartbeat, and
 * terminal-message semantics. Decoupled from React so it can be
 * shared by route-level hooks (`useLiveStream`, `useChatStream`)
 * and by background services (e.g. the global proposals subscriber).
 *
 * The backend uses query-string fallbacks for tenancy because
 * browsers don't allow custom WS headers. We append every X-AQP-*
 * value as `aqp_<lowercased>` query params; FastAPI's WS route
 * dependency reads either header or query.
 */
export function createWsClient<TIn = unknown, TOut = unknown>(
  options: WsClientOptions<TIn>,
): WsClient<TOut> {
  const {
    path,
    onMessage,
    onStatus,
    isTerminal,
    reconnect = true,
    backoffMs = DEFAULT_BACKOFF,
    maxBackoffMs = DEFAULT_MAX_BACKOFF,
    heartbeat,
  } = options;

  let ws: WebSocket | null = null;
  let status: WsStatus = "idle";
  let attempts = 0;
  let heartbeatHandle: ReturnType<typeof setInterval> | null = null;
  let reopenHandle: ReturnType<typeof setTimeout> | null = null;
  let manuallyClosed = false;

  const setStatus = (next: WsStatus) => {
    status = next;
    onStatus?.(next);
  };

  const stopHeartbeat = () => {
    if (heartbeatHandle != null) {
      clearInterval(heartbeatHandle);
      heartbeatHandle = null;
    }
  };

  const startHeartbeat = (socket: WebSocket) => {
    stopHeartbeat();
    if (!heartbeat) return;
    heartbeatHandle = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(
          typeof heartbeat.payload === "string"
            ? heartbeat.payload
            : JSON.stringify(heartbeat.payload),
        );
      }
    }, heartbeat.intervalMs);
  };

  const buildUrl = () => {
    const url = new URL(wsUrl(path));
    const headers = getTenancyHeaders();
    for (const [key, value] of Object.entries(headers)) {
      const qsKey = `aqp_${key.replace(/^X-AQP-/i, "").toLowerCase()}`;
      if (!url.searchParams.has(qsKey)) {
        url.searchParams.set(qsKey, value);
      }
    }
    return url.toString();
  };

  const open = () => {
    if (ws && ws.readyState <= WebSocket.OPEN) return;
    manuallyClosed = false;
    setStatus("connecting");
    let socket: WebSocket;
    try {
      socket = new WebSocket(buildUrl());
    } catch {
      setStatus("error");
      return;
    }
    ws = socket;
    socket.onopen = () => {
      attempts = 0;
      setStatus("open");
      startHeartbeat(socket);
    };
    socket.onmessage = (event) => {
      let parsed: TIn;
      try {
        parsed = JSON.parse(event.data) as TIn;
      } catch {
        parsed = event.data as unknown as TIn;
      }
      onMessage(parsed);
      if (isTerminal?.(parsed)) {
        manuallyClosed = true;
        socket.close();
      }
    };
    socket.onerror = () => {
      setStatus("error");
    };
    socket.onclose = () => {
      stopHeartbeat();
      setStatus("closed");
      ws = null;
      if (reconnect && !manuallyClosed) {
        const delay = Math.min(backoffMs * 2 ** attempts, maxBackoffMs);
        attempts += 1;
        reopenHandle = setTimeout(open, delay);
      }
    };
  };

  open();

  return {
    status: () => status,
    send: (msg) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(typeof msg === "string" ? msg : JSON.stringify(msg));
    },
    close: () => {
      manuallyClosed = true;
      stopHeartbeat();
      if (reopenHandle != null) {
        clearTimeout(reopenHandle);
        reopenHandle = null;
      }
      ws?.close();
      ws = null;
    },
    reopen: () => {
      manuallyClosed = false;
      open();
    },
  };
}
