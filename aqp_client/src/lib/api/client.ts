import { getAccessToken, hasAuthBackend } from "@/lib/auth/tokenStore";
import { getTenancyHeaders } from "@/store/tenancy";

import { API_BASE_URL } from "./config";

/**
 * Surfaces FastAPI's `{detail: ...}` error payload as a typed exception
 * so callers can branch on `error.status` (e.g. 404 -> stub UI, 401 ->
 * tenancy refresh, 403 -> insufficient role on workspace/project).
 */
export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/**
 * `exactOptionalPropertyTypes: true` requires that any callsite passing
 * `query: undefined` is typed exactly as `query?: Record<...>` here. We
 * lift the constraint by spelling the optional field as either present
 * with a real value or missing entirely.
 */
type ApiFetchInit = Omit<RequestInit, "body"> & {
  query?: Record<string, string | number | boolean | undefined | null> | undefined;
  body?: BodyInit | null | undefined;
};

/**
 * Tenancy-aware fetch wrapper used everywhere except the openapi-fetch
 * generated client. Injects X-AQP-* headers on every call, normalises
 * errors to {@link ApiError}, and JSON-decodes responses. Falls back to
 * text for non-JSON content types.
 *
 * Default `credentials: "omit"` mirrors the existing webui behaviour:
 * with `Access-Control-Allow-Origin: *` (FastAPI's CORS default when no
 * whitelist is set) browsers reject `credentials: "include"`. The REST
 * API does not rely on cross-site cookies today.
 */
export async function apiFetch<T = unknown>(
  path: string,
  init: ApiFetchInit = {},
): Promise<T> {
  const { query, credentials = "omit", headers, body, method = "GET", ...rest } = init;
  const url = new URL(
    path.startsWith("http") ? path : `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`,
    typeof window !== "undefined" ? window.location.href : "http://localhost",
  );
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null) continue;
      url.searchParams.set(k, String(v));
    }
  }

  const composedHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(body && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
    ...getTenancyHeaders(),
    ...(headers as Record<string, string> | undefined),
  };

  // OIDC mode: the AuthProvider has installed an access-token getter
  // into tokenStore. Pull a fresh JWT on every call (the SDK caches +
  // refreshes silently). In local-first deployments hasAuthBackend()
  // returns false and we skip Authorization entirely so the FastAPI
  // dep falls through to the deterministic default-user.
  if (hasAuthBackend() && !composedHeaders.Authorization) {
    const token = await getAccessToken();
    if (token) {
      composedHeaders.Authorization = `Bearer ${token}`;
    }
  }

  const fetchInit: RequestInit = {
    method,
    headers: composedHeaders,
    credentials,
    ...rest,
  };
  if (body != null) fetchInit.body = body;
  const response = await fetch(url.toString(), fetchInit);

  if (!response.ok) {
    let errBody: unknown = null;
    try {
      errBody = await response.clone().json();
    } catch {
      try {
        errBody = await response.clone().text();
      } catch {
        errBody = null;
      }
    }
    const detail =
      (errBody as { detail?: string })?.detail ??
      response.statusText ??
      `HTTP ${response.status}`;
    throw new ApiError(response.status, String(detail), errBody);
  }
  if (response.status === 204) return undefined as T;
  const ct = response.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}
