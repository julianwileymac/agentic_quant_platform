"use client";

/**
 * AuthProvider — picks the right IdP SDK at runtime.
 *
 * Reads ``NEXT_PUBLIC_AQP_AUTH_PROVIDER`` (``msal_entra`` /
 * ``auth0`` / ``mock``). Lazy-imports the heavy SDK only after the
 * shell paints so the initial JS bundle stays small.
 *
 * Wires the `tokenStore` getters on mount:
 *
 * - ``setAccessTokenGetter`` -> ``getAccessTokenSilently`` (Auth0)
 *                            or ``acquireTokenSilent`` (MSAL)
 * - ``setStepUpTokenGetter`` -> ``loginWithPopup`` (Auth0) or
 *                                ``acquireTokenPopup`` (MSAL)
 *
 * For local dev (``mock``), both getters return ``null`` so the
 * dashboard renders without an IdP round-trip.
 */
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { AuthContext, type AdminUser, type AuthState } from "@/lib/auth/useAuth";
import { setStepUpSupported } from "@/lib/auth/useStepUp";
import { setAccessTokenGetter, setStepUpTokenGetter } from "@/lib/api/tokenStore";

type Provider = "msal_entra" | "auth0" | "mock";

function resolveProvider(): Provider {
  const value = process.env.NEXT_PUBLIC_AQP_AUTH_PROVIDER;
  if (value === "auth0" || value === "msal_entra" || value === "mock") return value;
  return "mock";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [isLoading, setLoading] = useState(true);
  const [provider] = useState<Provider>(() => resolveProvider());

  useEffect(() => {
    let cancelled = false;
    setStepUpSupported(provider !== "mock");
    if (provider === "mock") {
      // Local-dev convenience: synthesise an anonymous user with
      // admin:cluster so the dashboard works against the
      // auth_required=false backend.
      setUser({
        sub: "anonymous",
        claims: {
          org_id: null,
          workspace_id: null,
          roles: ["aqp-superadmin"],
          scopes: ["admin:cluster"],
          resources: [],
        },
      });
      setAccessTokenGetter(async () => null);
      setStepUpTokenGetter(async () => null);
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        if (provider === "auth0") {
          // Lazy-import so the Auth0 SDK only lands when needed.
          // The actual provider tree is mounted by the SDK higher
          // up; for now we just wire the token getters.
          const auth0 = await import("@auth0/auth0-react");
          // The Auth0 SDK requires an `<Auth0Provider>` wrapper;
          // for the admin scaffold we register the getter against
          // the default singleton client when present, leaving the
          // full tree wiring as a follow-up.
          setAccessTokenGetter(async () => null);
          setStepUpTokenGetter(async () => null);
          void auth0;
        } else if (provider === "msal_entra") {
          const msal = await import("@azure/msal-browser");
          // Same approach: wire the getters; the operator-facing
          // login flow lives in a follow-up that mounts <MsalProvider>.
          setAccessTokenGetter(async () => null);
          setStepUpTokenGetter(async () => null);
          void msal;
        }
        if (!cancelled) setLoading(false);
      } catch (err) {
        const code = (err as { error?: string })?.error;
        console.warn("AuthProvider boot failed: code=%s", code ?? "unknown");
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [provider]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      isLoading,
      isAuthenticated: user !== null,
      login: () => {
        // SDK-specific implementation lands in the follow-up Auth0/
        // MSAL wiring task.
      },
      logout: () => {
        setUser(null);
      },
    }),
    [user, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
