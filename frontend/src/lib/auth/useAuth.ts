import { useAuth0 } from "@auth0/auth0-react";
import { useCallback, useMemo } from "react";

import { authConfig, isAuthEnabled } from "./config";

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
  };
  loginWithRedirect: (returnTo?: string, opts?: { organization?: string }) => Promise<void>;
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
  roles: ["owner"],
};

const CLAIMS_NS = "https://aqp/";

export function useAuth(): AuthSurface {
  if (!isAuthEnabled()) {
    return {
      enabled: false,
      isLoading: false,
      isAuthenticated: true,
      user: LOCAL_DEFAULT,
      claims: LOCAL_CLAIMS,
      loginWithRedirect: async () => {},
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
    return { orgId: null, teamId: null, workspaceId: null, roles: [] };
  }
  const orgId =
    (user[`${CLAIMS_NS}org_id`] as string | undefined) ??
    (user.org_id as string | undefined) ??
    null;
  const teamId =
    (user[`${CLAIMS_NS}team_id`] as string | undefined) ??
    (user.team_id as string | undefined) ??
    null;
  const workspaceId =
    (user[`${CLAIMS_NS}workspace_id`] as string | undefined) ??
    (user.workspace_id as string | undefined) ??
    null;
  const rolesRaw =
    (user[`${CLAIMS_NS}roles`] as string[] | undefined) ??
    (user.roles as string[] | undefined) ??
    [];
  return {
    orgId: orgId ?? null,
    teamId: teamId ?? null,
    workspaceId: workspaceId ?? null,
    roles: Array.isArray(rolesRaw) ? rolesRaw.map(String) : [],
  };
}

function useAuthEnabled(): AuthSurface {
  const a0 = useAuth0();

  const loginWithRedirect = useCallback(
    async (returnTo?: string, opts?: { organization?: string }) => {
      const appState = returnTo ? { returnTo } : undefined;
      const authorizationParams = opts?.organization
        ? { organization: opts.organization }
        : undefined;
      await a0.loginWithRedirect({
        ...(appState ? { appState } : {}),
        ...(authorizationParams ? { authorizationParams } : {}),
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
      claims: _claimsFromUser(a0.user as Record<string, unknown> | undefined),
      loginWithRedirect,
      logout,
      getClaims,
    }),
    [a0.isLoading, a0.isAuthenticated, a0.user, loginWithRedirect, logout, getClaims],
  );
}
