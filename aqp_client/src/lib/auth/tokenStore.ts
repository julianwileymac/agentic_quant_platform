/**
 * Module-level singleton holding the latest access-token getter.
 *
 * The frontend's API client (`apiFetch` in `lib/api/client.ts`) is not
 * React; it can't call `useAuth0()`. Instead the `<AuthProvider>` calls
 * `setAccessTokenGetter` once it boots, and `apiFetch` calls
 * `getAccessTokenSilently()` on every request that needs Authorization.
 *
 * In local-first deployments the getter stays unset and `apiFetch`
 * skips the Authorization header entirely — `aqp.auth.deps.current_user`
 * falls through to the deterministic default-user row.
 *
 * The getter returns ``null`` on transient failure (e.g. silent token
 * refresh fails because the IdP session expired). The api client
 * surfaces 401s up to the route layer which redirects to /auth/login.
 */

export type AccessTokenGetter = () => Promise<string | null>;

/**
 * Hint passed by ``apiFetch`` when a route just returned 401 with an
 * RFC 9470 ``WWW-Authenticate: Bearer error="insufficient_user_authentication"``
 * header. The wired getter (Auth0 or MSAL) MUST call its silent-refresh
 * variant with ``acr_values`` + ``max_age: 0`` so the IdP forces an
 * interactive MFA challenge before returning a fresh token.
 *
 * The value matches the OIDC ``acr_values`` parameter; defaults to the
 * standard ``http://schemas.openid.net/pape/policies/2007/06/multi-factor``
 * policy URI. See :mod:`aqp.api.security_stepup`.
 */
export type StepUpHint = {
  acr_values?: string;
  max_age?: number;
};

export type StepUpTokenGetter = (hint?: StepUpHint) => Promise<string | null>;

let getter: AccessTokenGetter | null = null;
let stepUpGetter: StepUpTokenGetter | null = null;

export function setAccessTokenGetter(fn: AccessTokenGetter | null): void {
  getter = fn;
}

/**
 * Install a step-up-capable token getter. When the backend rejects a
 * request with ``insufficient_user_authentication``, ``apiFetch`` calls
 * this and retries the original request once with the freshly minted
 * token. AuthProvider wires this to ``loginWithPopup`` / ``acquireTokenPopup``
 * so the user transparently gets prompted for MFA and the original
 * destructive action completes.
 */
export function setStepUpTokenGetter(fn: StepUpTokenGetter | null): void {
  stepUpGetter = fn;
}

export async function getAccessToken(): Promise<string | null> {
  if (!getter) return null;
  try {
    return await getter();
  } catch (err) {
    const code = (err as { error?: string })?.error;
    console.warn("getAccessToken failed: code=%s", code ?? "unknown");
    return null;
  }
}

/**
 * Synchronously request a fresh, MFA-bound token for a sensitive call.
 *
 * Returns ``null`` when the user cancels the MFA prompt, the IdP
 * session is in a state that cannot be interactively recovered, or no
 * step-up getter is wired (local-dev with ``AQP_AUTH_PROVIDER=local``).
 *
 * Note: this performs an interactive prompt (popup or redirect under
 * the hood depending on provider). Callers should ALREADY have surfaced
 * a "this needs re-auth" UI to the user before calling it.
 */
export async function requestStepUpToken(hint?: StepUpHint): Promise<string | null> {
  if (!stepUpGetter) return null;
  try {
    return await stepUpGetter(hint);
  } catch (err) {
    const code = (err as { error?: string })?.error;
    console.warn("requestStepUpToken failed: code=%s", code ?? "unknown");
    return null;
  }
}

export function hasAuthBackend(): boolean {
  return getter !== null;
}

export function hasStepUpSupport(): boolean {
  return stepUpGetter !== null;
}
