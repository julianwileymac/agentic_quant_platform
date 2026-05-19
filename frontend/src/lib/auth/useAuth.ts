import { useAuth0 } from "@auth0/auth0-react";
import { useCallback, useMemo } from "react";

import { authConfig, isAuthEnabled, isAuthRequired } from "./config";

/**
 * Identity surface for the rest of the app. Returns the same shape
 * regardless of whether OIDC is enabled, so route components can
 * branch on `isAuthenticated` instead of repeatedly checking
 * `isAuthEnabled()`.
 *
 * When OIDC is disabled (local-first dev), the hook synthesises a
 * "permanently logged in" identity matching the deterministic
 * default-user row. The `/auth/whoami` API still resolves the same
 * default — keep them in sync via `frontend/src/store/tenancy.ts`.
 */
export interface AuthSurface {
  enabled: boolean;
  isLoading: boolean;
  isAuthenticated: boolean;
  user: {
    id: string | null;
    email: string | null;
    name: string | null;
    picture: string | null;
  };
  /**
   * AQP-namespaced custom claims injected by the Auth0 Action (see
   * ``docs/auth0-actions.md``). Phase 4/6 use these to hydrate the
   * tenancy store + drive the ContextBar without an extra round-trip.
   */
  claims: {
    orgId: string | null;
    teamId: string | null;
    workspaceId: string | null;
    roles: string[];
    /**
     * Explicit resource IDs the user is allowed to see (ADR 003).
     * Operators on `aqp-superadmin` (`admin:cluster` scope) bypass
     * resource filtering server-side; UI uses `hasScope('admin:cluster')`
     * to decide whether to render the "show everything" toggle.
     */
    resources: string[];
    /**
     * Granted RBAC scopes — read:infrastructure, manage:agents,
     * manage:infrastructure, admin:cluster. Sourced from the
     * AQP-namespaced `scopes` claim plus Auth0's `permissions` array.
     */
    scopes: string[];
  };
  /**
   * Convenience helper for scope-gated nav items. Returns true when the
   * user has the requested scope OR admin:cluster (which bypasses all
   * resource filtering).
   */
  hasScope: (scope: string) => boolean;
  /**
   * Returns true when the resource is in the user's resources claim,
   * OR the user has admin:cluster. Convenience helper for permission-
   * aware UI rendering.
   */
  canSeeResource: (resourceId: string) => boolean;
  loginWithRedirect: (returnTo?: string, opts?: { organization?: string }) => Promise<void>;
  loginWithMicrosoft: (returnTo?: string) => Promise<void>;
  loginWithGoogle: (returnTo?: string) => Promise<void>;
  signupWithRedirect: (returnTo?: string) => Promise<void>;
  forgotPassword: (returnTo?: string) => Promise<void>;
  logout: () => Promise<void>;
  /**
   * Reads the cached id token claim set; useful for the identity chip
   * UI but never used for authorization (the backend re-validates the
   * access token on every request).
   */
  getClaims: () => Promise<Record<string, unknown> | null>;
}

const LOCAL_DEFAULT: AuthSurface["user"] = {
  id: "00000000-0000-0000-0000-000000000003",
  email: "local@aqp.dev",
  name: "Local User",
  picture: null,
};

const LOCAL_CLAIMS: AuthSurface["claims"] = {
  orgId: "00000000-0000-0000-0000-000000000001",
  teamId: "00000000-0000-0000-0000-000000000002",
  workspaceId: "00000000-0000-0000-0000-000000000004",
  roles: ["owner", "aqp-superadmin"],
  resources: [],
  scopes: ["admin:cluster"], // local dev sees everything
};

// Canonical claims namespace per ADR 003. Legacy `https://aqp/` is
// still read (one-release backward compatibility) — the backend's
// post-login Action will move to the canonical namespace first, with
// the alias kept around until existing tokens age out.
const CLAIMS_NS_CANONICAL = "https://aqp.internal/";
const CLAIMS_NS_LEGACY = "https://aqp/";
const CLAIMS_NS_LIST = [CLAIMS_NS_CANONICAL, CLAIMS_NS_LEGACY] as const;
const DEFAULT_MS_CONNECTION = "azure-ad-myorg";
const DEFAULT_GOOGLE_CONNECTION = "google-oauth2";

function readNamespacedClaim<T>(
  user: Record<string, unknown> | undefined,
  field: string,
): T | undefined {
  if (!user) return undefined;
  for (const ns of CLAIMS_NS_LIST) {
    const key = `${ns}${field}`;
    if (user[key] !== undefined) {
      return user[key] as T;
    }
  }
  return undefined;
}

function readStringEnv(key: string, fallback: string): string {
  const value = (import.meta.env as Record<string, string | undefined>)[key];
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

function baseAuth0AuthorizationParams(): {
  redirect_uri: string;
  audience: string;
  scope: string;
} {
  return {
    redirect_uri: authConfig.redirectUri,
    audience: authConfig.audience,
    scope: authConfig.scope,
  };
}

export function useAuth(): AuthSurface {
  if (!isAuthEnabled()) {
    const required = isAuthRequired();
    return {
      enabled: false,
      isLoading: false,
      isAuthenticated: !required,
      user: LOCAL_DEFAULT,
      claims: LOCAL_CLAIMS,
      hasScope: (scope: string) =>
        LOCAL_CLAIMS.scopes.includes(scope) ||
        LOCAL_CLAIMS.scopes.includes("admin:cluster"),
      canSeeResource: () => true, // local dev bypasses resource filtering
      loginWithRedirect: async () => {},
      loginWithMicrosoft: async () => {},
      loginWithGoogle: async () => {},
      signupWithRedirect: async () => {},
      forgotPassword: async () => {},
      logout: async () => {},
      getClaims: async () => null,
    };
  }
  // The hook is only safe to call inside <Auth0Provider>; the no-auth
  // branch above prevents that under VITE_AUTH0_DOMAIN= unset builds.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useAuthEnabled();
}

function _claimsFromUser(
  user: Record<string, unknown> | undefined,
): AuthSurface["claims"] {
  if (!user) {
    return {
      orgId: null,
      teamId: null,
      workspaceId: null,
      roles: [],
      resources: [],
      scopes: [],
    };
  }
  const orgId =
    readNamespacedClaim<string>(user, "org_id") ??
    (user.org_id as string | undefined) ??
    null;
  const teamId =
    readNamespacedClaim<string>(user, "team_id") ??
    (user.team_id as string | undefined) ??
    null;
  const workspaceId =
    readNamespacedClaim<string>(user, "workspace_id") ??
    (user.workspace_id as string | undefined) ??
    null;
  const rolesRaw =
    readNamespacedClaim<string[]>(user, "roles") ??
    (user.roles as string[] | undefined) ??
    [];
  const resourcesRaw =
    readNamespacedClaim<string[]>(user, "resources") ??
    (user.resources as string[] | undefined) ??
    [];
  const scopesRaw =
    readNamespacedClaim<string[]>(user, "scopes") ??
    (user.scopes as string[] | undefined) ??
    [];
  // Auth0's RBAC injects `permissions` (array) on the access token.
  const permsRaw = (user.permissions as string[] | undefined) ?? [];
  const scopeStr = (user.scope as string | undefined) ?? "";
  const scopesFromString = scopeStr ? scopeStr.split(/\s+/).filter(Boolean) : [];
  const scopes = Array.from(
    new Set(
      [
        ...(Array.isArray(scopesRaw) ? scopesRaw : []),
        ...(Array.isArray(permsRaw) ? permsRaw : []),
        ...scopesFromString,
      ].map(String),
    ),
  );
  return {
    orgId: orgId ?? null,
    teamId: teamId ?? null,
    workspaceId: workspaceId ?? null,
    roles: Array.isArray(rolesRaw) ? rolesRaw.map(String) : [],
    resources: Array.isArray(resourcesRaw) ? resourcesRaw.map(String) : [],
    scopes,
  };
}

function useAuthEnabled(): AuthSurface {
  const a0 = useAuth0();
  const msConnection = readStringEnv("VITE_AUTH0_MS_CONNECTION", DEFAULT_MS_CONNECTION);
  const googleConnection = readStringEnv("VITE_AUTH0_GOOGLE_CONNECTION", DEFAULT_GOOGLE_CONNECTION);

  const loginWithRedirect = useCallback(
    async (returnTo?: string, opts?: { organization?: string }) => {
      const appState = returnTo ? { returnTo } : undefined;
      const authorizationParams = {
        ...baseAuth0AuthorizationParams(),
        ...(opts?.organization ? { organization: opts.organization } : {}),
      };
      await a0.loginWithRedirect({
        ...(appState ? { appState } : {}),
        authorizationParams,
      });
    },
    [a0],
  );

  const loginWithMicrosoft = useCallback(
    async (returnTo?: string) => {
      const appState = returnTo ? { returnTo } : undefined;
      await a0.loginWithRedirect({
        ...(appState ? { appState } : {}),
        authorizationParams: {
          ...baseAuth0AuthorizationParams(),
          connection: msConnection,
        },
      });
    },
    [a0, msConnection],
  );

  const loginWithGoogle = useCallback(
    async (returnTo?: string) => {
      const appState = returnTo ? { returnTo } : undefined;
      await a0.loginWithRedirect({
        ...(appState ? { appState } : {}),
        authorizationParams: {
          ...baseAuth0AuthorizationParams(),
          connection: googleConnection,
        },
      });
    },
    [a0, googleConnection],
  );

  const signupWithRedirect = useCallback(
    async (returnTo?: string) => {
      const appState = returnTo ? { returnTo } : undefined;
      await a0.loginWithRedirect({
        ...(appState ? { appState } : {}),
        authorizationParams: {
          ...baseAuth0AuthorizationParams(),
          screen_hint: "signup",
        },
      });
    },
    [a0],
  );

  const forgotPassword = useCallback(
    async (returnTo?: string) => {
      const appState = returnTo ? { returnTo } : undefined;
      await a0.loginWithRedirect({
        ...(appState ? { appState } : {}),
        authorizationParams: {
          ...baseAuth0AuthorizationParams(),
          screen_hint: "reset",
        },
      });
    },
    [a0],
  );

  const logout = useCallback(async () => {
    a0.logout({
      logoutParams: {
        returnTo: typeof window !== "undefined" ? window.location.origin : authConfig.redirectUri,
      },
    });
  }, [a0]);

  const getClaims = useCallback(async () => {
    const claims = await a0.getIdTokenClaims();
    return (claims as Record<string, unknown>) ?? null;
  }, [a0]);

  const claims = useMemo(
    () => _claimsFromUser(a0.user as Record<string, unknown> | undefined),
    [a0.user],
  );

  const hasScope = useCallback(
    (scope: string) =>
      claims.scopes.includes(scope) || claims.scopes.includes("admin:cluster"),
    [claims.scopes],
  );

  const canSeeResource = useCallback(
    (resourceId: string) =>
      claims.scopes.includes("admin:cluster") ||
      claims.resources.includes(resourceId),
    [claims.scopes, claims.resources],
  );

  return useMemo<AuthSurface>(
    () => ({
      enabled: true,
      isLoading: Boolean(a0.isLoading),
      isAuthenticated: Boolean(a0.isAuthenticated),
      user: {
        id: (a0.user?.sub as string | undefined) ?? null,
        email: (a0.user?.email as string | undefined) ?? null,
        name:
          (a0.user?.name as string | undefined) ??
          (a0.user?.nickname as string | undefined) ??
          null,
        picture: (a0.user?.picture as string | undefined) ?? null,
      },
      claims,
      hasScope,
      canSeeResource,
      loginWithRedirect,
      loginWithMicrosoft,
      loginWithGoogle,
      signupWithRedirect,
      forgotPassword,
      logout,
      getClaims,
    }),
    [
      a0.isLoading,
      a0.isAuthenticated,
      a0.user,
      claims,
      hasScope,
      canSeeResource,
      loginWithRedirect,
      loginWithMicrosoft,
      loginWithGoogle,
      signupWithRedirect,
      forgotPassword,
      logout,
      getClaims,
    ],
  );
}
