"use client";

/**
 * AuthProvider - wires the Microsoft Entra (MSAL) login flow for the
 * AQP staff admin SPA.
 *
 * Reads NEXT_PUBLIC_AQP_AUTH_PROVIDER to pick the SDK:
 *   - msal_entra (default in production) - full MSAL flow.
 *   - auth0 - placeholder (kept for B2C fallback).
 *   - mock - local-dev anonymous user with admin:cluster.
 *
 * For msal_entra the provider:
 *   1. Fetches /admin/auth/discovery from the backend BFF to learn
 *      the authority / client_id / scopes WITHOUT hard-coding tenant
 *      ids in the bundle.
 *   2. Constructs a PublicClientApplication and calls
 *      handleRedirectPromise() so the post-login round-trip is
 *      consumed cleanly.
 *   3. Wires acquireTokenSilent into the access-token getter and
 *      acquireTokenPopup into the step-up getter.
 *
 * The SPA NEVER stores tokens directly - MSAL's session cache (default
 * sessionStorage) is the only place the JWT lives. The backend BFF is
 * the source of truth for everything else.
 */
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AuthContext, type AdminUser, type AuthState } from "@/lib/auth/useAuth";
import { setStepUpSupported } from "@/lib/auth/useStepUp";
import { setAccessTokenGetter, setStepUpTokenGetter } from "@/lib/api/tokenStore";

type Provider = "msal_entra" | "auth0" | "mock";

interface DiscoveryDoc {
  provider: Provider;
  auth_enabled: boolean;
  issuer?: string;
  authority?: string;
  client_id?: string;
  audience?: string;
  scopes?: string[];
  redirect_path?: string;
  tenant_id?: string;
  jwks_uri?: string;
}

function resolveProvider(): Provider {
  const value = process.env.NEXT_PUBLIC_AQP_AUTH_PROVIDER;
  if (value === "auth0" || value === "msal_entra" || value === "mock") return value;
  return "mock";
}

function backendBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_AQP_ADMIN_API_URL ||
    process.env.NEXT_PUBLIC_AQP_ADMIN_BACKEND_URL ||
    ""
  ).replace(/\/$/, "");
}

async function fetchDiscovery(): Promise<DiscoveryDoc> {
  const base = backendBaseUrl();
  const res = await fetch(`${base}/admin/auth/discovery`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`discovery failed: HTTP ${res.status}`);
  return (await res.json()) as DiscoveryDoc;
}

interface AccountLike {
  homeAccountId?: string;
  username?: string;
  name?: string;
  idTokenClaims?: Record<string, unknown>;
}

function accountToAdmin(account: AccountLike | null): AdminUser | null {
  if (!account) return null;
  const claims = (account.idTokenClaims ?? {}) as Record<string, unknown>;
  const roles = Array.isArray(claims.roles)
    ? (claims.roles as unknown[]).map(String)
    : [];
  const groups = Array.isArray(claims.groups)
    ? (claims.groups as unknown[]).map(String)
    : [];
  // Scopes come from the access-token's scp claim, but for the
  // ID-token-only path (silent-login round-trip) we surface roles
  // through the same shape so route guards keep working.
  const scopes: string[] = [];
  if (typeof claims.scp === "string") {
    scopes.push(...(claims.scp as string).split(" ").filter(Boolean));
  }
  return {
    sub: String(claims.oid || claims.sub || account.homeAccountId || ""),
    email: account.username,
    name: account.name,
    claims: {
      org_id: (claims.org_id as string | undefined) ?? null,
      workspace_id: (claims.workspace_id as string | undefined) ?? null,
      roles,
      scopes,
      resources: groups,
    },
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [isLoading, setLoading] = useState(true);
  const [provider] = useState<Provider>(() => resolveProvider());
  const pcaRef = useRef<unknown | null>(null);
  const discoveryRef = useRef<DiscoveryDoc | null>(null);

  const login = useCallback(() => {
    if (provider !== "msal_entra") return;
    const pca = pcaRef.current as
      | { loginRedirect: (req: unknown) => Promise<void> }
      | null;
    const disc = discoveryRef.current;
    if (!pca || !disc?.scopes) {
      console.warn("AuthProvider.login(): MSAL not yet ready");
      return;
    }
    void pca.loginRedirect({ scopes: disc.scopes });
  }, [provider]);

  const logout = useCallback(() => {
    if (provider !== "msal_entra") {
      setUser(null);
      return;
    }
    const pca = pcaRef.current as
      | { logoutRedirect: (req: unknown) => Promise<void> }
      | null;
    if (!pca) {
      setUser(null);
      return;
    }
    void pca.logoutRedirect({});
  }, [provider]);

  useEffect(() => {
    let cancelled = false;
    setStepUpSupported(provider !== "mock");

    // -------- Mock: local-dev anonymous user. --------
    if (provider === "mock") {
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

    // -------- Auth0 placeholder (B2C fallback path). --------
    if (provider === "auth0") {
      void (async () => {
        try {
          await import("@auth0/auth0-react");
          setAccessTokenGetter(async () => null);
          setStepUpTokenGetter(async () => null);
        } catch (err) {
          const code = (err as { error?: string })?.error;
          console.warn("Auth0 boot failed: code=%s", code ?? "unknown");
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
      return () => {
        cancelled = true;
      };
    }

    // -------- MSAL Entra (the canonical staff path). --------
    void (async () => {
      try {
        const discovery = await fetchDiscovery();
        if (!discovery.auth_enabled || discovery.provider !== "msal_entra") {
          // Backend reports auth disabled - fall back to anonymous.
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
          if (!cancelled) setLoading(false);
          return;
        }
        if (!discovery.client_id || !discovery.authority) {
          throw new Error(
            "discovery missing client_id/authority - backend env not set",
          );
        }
        discoveryRef.current = discovery;

        const msal = await import("@azure/msal-browser");
        const redirectUri =
          (typeof window !== "undefined" ? window.location.origin : "") +
          (discovery.redirect_path || "/api/auth/entra/callback");

        const pca = new msal.PublicClientApplication({
          auth: {
            clientId: discovery.client_id,
            authority: discovery.authority,
            redirectUri,
            postLogoutRedirectUri:
              typeof window !== "undefined" ? window.location.origin : "",
            navigateToLoginRequestUrl: true,
          },
          cache: {
            cacheLocation: "sessionStorage",
            storeAuthStateInCookie: false,
          },
        });
        // Required by msal-browser >= 4 before any other API call.
        if (
          typeof (pca as { initialize?: () => Promise<void> }).initialize ===
          "function"
        ) {
          await (pca as { initialize: () => Promise<void> }).initialize();
        }
        pcaRef.current = pca;

        // Consume any post-login redirect.
        const redirectResult = await pca.handleRedirectPromise();
        const account =
          redirectResult?.account ?? pca.getAllAccounts()[0] ?? null;
        if (account) {
          pca.setActiveAccount(account);
          setUser(accountToAdmin(account));
        }

        // Wire token getters into the shared store.
        setAccessTokenGetter(async () => {
          const acct = pca.getActiveAccount() ?? pca.getAllAccounts()[0];
          if (!acct) return null;
          try {
            const result = await pca.acquireTokenSilent({
              account: acct,
              scopes: discovery.scopes ?? [],
            });
            return result.accessToken ?? null;
          } catch (err) {
            const code = (err as { errorCode?: string })?.errorCode;
            console.warn(
              "acquireTokenSilent failed: code=%s",
              code ?? "unknown",
            );
            return null;
          }
        });

        setStepUpTokenGetter(async () => {
          try {
            const result = await pca.acquireTokenPopup({
              scopes: discovery.scopes ?? [],
              prompt: "login",
            });
            return result.accessToken ?? null;
          } catch (err) {
            const code = (err as { errorCode?: string })?.errorCode;
            console.warn(
              "acquireTokenPopup failed: code=%s",
              code ?? "unknown",
            );
            return null;
          }
        });

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
      login,
      logout,
    }),
    [user, isLoading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
