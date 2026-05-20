import { getAccessToken, hasAuthBackend } from "@/lib/auth/tokenStore";
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
 * Phase 3a authentication (the AQP control-plane maturation):
 * after `socket.onopen`, the client sends a first frame
 * `{"type":"auth","token":"<JWT>","workspace_id":"...","project_id":"...","lab_id":"..."}`
 * and waits for the server's `{"type":"auth_ok",...}` ACK before
 * surfacing the connection as "open" to React. The server-side
 * `WebSocketAuthenticator` (in `aqp/auth/ws.py`) validates the token
 * via the same path the HTTP layer uses (`validate_jwt`), constructs
 * a `RequestContext`, and binds the tenancy + scope set for the rest
 * of the session.
 *
 * Failure modes (server close codes):
 * - 4001 protocol error (malformed first frame, missing token)
 * - 4003 invalid / expired token
 * - 4008 insufficient scope
 *
 * Backwards compat: when `getAccessToken()` returns null (local-first
 * dev with no auth backend, or transient silent-refresh failure), we
 * still send an `auth` frame with `token: ""`. The server treats
 * empty tokens as "no first-frame auth" and falls back to the local
 * default context when `settings.ws_auth_required=false`.
 *
 * Tenancy fields are sent as part of the auth frame; legacy
 * `aqp_<header>` query params are also still attached to the URL so
 * the cutover stays compatible with older builds of the API.
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
  let authenticated = false;

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

  const buildAuthFrame = async (): Promise<string> => {
    const token = hasAuthBackend() ? await getAccessToken() : null;
    const headers = getTenancyHeaders();
    const overrides: Record<string, string> = {};
    for (const [key, value] of Object.entries(headers)) {
      const lower = key.replace(/^X-AQP-/i, "").toLowerCase();
      if (
        lower === "workspace" ||
        lower === "workspace_id" ||
        lower === "project" ||
        lower === "project_id" ||
        lower === "lab" ||
        lower === "lab_id"
      ) {
        // Normalise to the *_id form the backend authenticator expects.
        const normalised = lower.endsWith("_id") ? lower : `${lower}_id`;
        overrides[normalised] = value;
      }
    }
    return JSON.stringify({
      type: "auth",
      token: token ?? "",
      ...overrides,
    });
  };

  const open = () => {
    if (ws && ws.readyState <= WebSocket.OPEN) return;
    manuallyClosed = false;
    authenticated = false;
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
      // Send the Phase 3a first-frame auth payload BEFORE flipping
      // to "open" so subscribers don't try to send data before the
      // server's auth_ok ACK arrives.
      buildAuthFrame()
        .then((frame) => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(frame);
          }
        })
        .catch((err) => {
          console.warn("ws auth frame build failed:", err);
        });
    };
    socket.onmessage = (event) => {
      let parsed: TIn;
      try {
        parsed = JSON.parse(event.data) as TIn;
      } catch {
        parsed = event.data as unknown as TIn;
      }
      // Intercept the auth ACK / error frame BEFORE forwarding to
      // the route handler. Once auth_ok lands, surface "open" to
      // subscribers and start the heartbeat. auth_error frames are
      // followed by a server-initiated close so we don't need to
      // close the socket ourselves.
      if (!authenticated && typeof parsed === "object" && parsed !== null) {
        const tag = (parsed as { type?: unknown }).type;
        if (tag === "auth_ok") {
          authenticated = true;
          setStatus("open");
          startHeartbeat(socket);
          return;
        }
        if (tag === "auth_error") {
          // Server will close the socket immediately after this
          // frame; surfacing the error gives subscribers visibility.
          console.warn("ws auth error:", parsed);
          return;
        }
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
    socket.onclose = (event) => {
      stopHeartbeat();
      setStatus("closed");
      ws = null;
      // Don't auto-reconnect on terminal auth errors (4001/4003/4008)
      // because the next reconnect would fail with the same code.
      const terminalAuthCloseCodes = new Set([4001, 4003, 4008]);
      if (terminalAuthCloseCodes.has(event.code)) {
        manuallyClosed = true;
      }
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
      // Block outbound sends until the server has acknowledged auth so
      // route-level frames don't get mistaken for the auth payload.
      if (!authenticated) return;
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
