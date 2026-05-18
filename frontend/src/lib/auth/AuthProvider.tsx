import { Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import type { AppState } from "@auth0/auth0-react";
import { type ReactNode, useEffect } from "react";

import { authConfig, isAuthEnabled } from "./config";
import { setAccessTokenGetter } from "./tokenStore";

/**
 * Wrap the application in `<Auth0Provider>` when the SPA build was
 * given Auth0 credentials, otherwise render children directly. This
 * means local-first developer setups never load the Auth0 SDK at
 * runtime.
 *
 * The provider also installs the access-token getter into the
 * module-level `tokenStore` so `apiFetch` can attach
 * `Authorization: Bearer <jwt>` on every request without each route
 * having to thread the user object through.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  if (!isAuthEnabled()) {
    return <>{children}</>;
  }

  return (
    <Auth0Provider
      domain={authConfig.domain}
      clientId={authConfig.clientId}
      authorizationParams={{
        redirect_uri: authConfig.redirectUri,
        audience: authConfig.audience,
        scope: authConfig.scope,
        ...(authConfig.organization ? { organization: authConfig.organization } : {}),
      }}
      cacheLocation="localstorage"
      useRefreshTokens
      useRefreshTokensFallback={false}
      onRedirectCallback={(appState?: AppState) => {
        const target = appState?.returnTo || "/";
        if (typeof window !== "undefined") {
          window.history.replaceState({}, document.title, target);
        }
      }}
    >
      <TokenStoreBinder>{children}</TokenStoreBinder>
    </Auth0Provider>
  );
}

/**
 * Wires the Auth0 SDK's `getAccessTokenSilently` into the global token
 * store so the API client can attach `Authorization: Bearer` without
 * being a React component. Lives inside Auth0Provider's tree to call
 * `useAuth0()`.
 */
function TokenStoreBinder({ children }: { children: ReactNode }) {
  const { getAccessTokenSilently, isAuthenticated } = useAuth0();

  useEffect(() => {
    if (!isAuthenticated) {
      setAccessTokenGetter(null);
      return;
    }
    setAccessTokenGetter(async () => {
      try {
        const token = await getAccessTokenSilently({
          authorizationParams: {
            audience: authConfig.audience,
            scope: authConfig.scope,
          },
        });
        return token || null;
      } catch (err) {
        // login_required / consent_required mean the silent call failed;
        // returning null lets the api client choose how to react (most
        // routes will surface a 401 and the route guard will redirect).
        const code = (err as { error?: string })?.error;
        if (code !== "login_required" && code !== "consent_required") {
          console.warn("getAccessTokenSilently failed:", err);
        }
        return null;
      }
    });
    return () => setAccessTokenGetter(null);
  }, [isAuthenticated, getAccessTokenSilently]);

  return <>{children}</>;
}
