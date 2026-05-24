"use client";

import { createContext, useContext, useEffect, useState } from "react";

import type { AuthClaims, AuthUser } from "@/lib/auth/types";

interface AuthSurface {
  isLoading: boolean;
  isAuthenticated: boolean;
  user: AuthUser | null;
  claims: AuthClaims | null;
  provider: "auth0" | "entra" | "local" | null;
  hasScope: (scope: string) => boolean;
  canSeeResource: (resourceId: string) => boolean;
}

const DEFAULT: AuthSurface = {
  isLoading: true,
  isAuthenticated: false,
  user: null,
  claims: null,
  provider: null,
  hasScope: () => false,
  canSeeResource: () => false,
};

const AuthContext = createContext<AuthSurface>(DEFAULT);

export function useAuthClient(): AuthSurface {
  return useContext(AuthContext);
}

/**
 * Client-side hydration of the unified server-side session.
 *
 * The session itself is held in an httpOnly Secure SameSite=Lax cookie
 * (AGENTS rule 4); the client cannot read it. This provider calls
 * /api/auth/me on mount to surface non-sensitive identity + claims to
 * components that need them (e.g., the OrgSwitcher in the dashboard
 * shell). Mirrors aqp_client/src/lib/auth/useAuth.ts.
 */
export function AuthClientProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [state, setState] = useState<AuthSurface>(DEFAULT);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/me", {
          credentials: "include",
          cache: "no-store",
        });
        if (cancelled) return;
        if (!res.ok) {
          setState({
            ...DEFAULT,
            isLoading: false,
            isAuthenticated: false,
          });
          return;
        }
        const data = await res.json();
        const claims = data.claims as AuthClaims | null;
        const scopes = new Set(claims?.scopes ?? []);
        const resources = new Set(claims?.resources ?? []);
        const isAdmin = scopes.has("admin:cluster");
        setState({
          isLoading: false,
          isAuthenticated: Boolean(data.user),
          user: data.user ?? null,
          claims,
          provider: data.provider ?? null,
          hasScope: (s) => scopes.has(s) || isAdmin,
          canSeeResource: (id) => isAdmin || resources.has(id),
        });
      } catch {
        if (cancelled) return;
        setState({ ...DEFAULT, isLoading: false });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}
