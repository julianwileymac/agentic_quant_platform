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

let getter: AccessTokenGetter | null = null;

export function setAccessTokenGetter(fn: AccessTokenGetter | null): void {
  getter = fn;
}

export async function getAccessToken(): Promise<string | null> {
  if (!getter) return null;
  try {
    return await getter();
  } catch (err) {
    console.warn("getAccessToken failed:", err);
    return null;
  }
}

export function hasAuthBackend(): boolean {
  return getter !== null;
}
