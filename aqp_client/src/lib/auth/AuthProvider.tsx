import { Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import type { AppState } from "@auth0/auth0-react";
import { type ReactNode, useEffect } from "react";

import { authConfig, isAuthEnabled } from "./config";
import { MsalProvider } from "./MsalProvider";
import { setAccessTokenGetter, setStepUpTokenGetter, type StepUpHint } from "./tokenStore";

/**
 * Multi-IdP wrapper for the Vite frontend.
 *
 * Mounts the matching SDK based on the build-time configuration
 * surfaced by `authConfig.provider`:
 *
 * - `msal_entra` -> `<MsalProvider>` (`@azure/msal-react`)
 * - `auth0`      -> `<Auth0Provider>` (`@auth0/auth0-react`)
 * - `local`      -> children directly (no IdP at all)
 *
 * Per the 2026 multi-IdP guidance (Microsoft Q&A 5588463) the SPA
 * picks ONE provider at boot and instantiates `PublicClientApplication`
 * lazily — there is no clean way to nest multiple MSAL providers, so
 * deployments that need Auth0 + Entra side-by-side route through the
 * AQP BFF (`/auth/providers`) and pick at the user level.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  if (!isAuthEnabled()) {
    return <>{children}</>;
  }

  if (authConfig.provider === "msal_entra") {
    return <MsalProvider>{children}</MsalProvider>;
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
      <Auth0TokenStoreBinder>{children}</Auth0TokenStoreBinder>
    </Auth0Provider>
  );
}

/**
 * Wires the Auth0 SDK's `getAccessTokenSilently` into the global token
 * store so the API client can attach `Authorization: Bearer` without
 * being a React component. Lives inside Auth0Provider's tree to call
 * `useAuth0()`. The MSAL branch lives in `MsalProvider.tsx`.
 */
function Auth0TokenStoreBinder({ children }: { children: ReactNode }) {
  const { getAccessTokenSilently, getAccessTokenWithPopup, isAuthenticated } = useAuth0();

  useEffect(() => {
    if (!isAuthenticated) {
      setAccessTokenGetter(null);
      setStepUpTokenGetter(null);
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
        // We deliberately do NOT include the err object in the log to
        // avoid leaking any embedded token material per the Management
        // Engine subagent rule.
        const code = (err as { error?: string })?.error;
        if (code !== "login_required" && code !== "consent_required") {
          console.warn("getAccessTokenSilently failed: code=%s", code ?? "unknown");
        }
        return null;
      }
    });
    // Step-up: force interactive MFA via popup. Auth0's
    // getAccessTokenWithPopup honours acr_values + max_age on
    // authorizationParams and routes through the IdP's MFA flow.
    setStepUpTokenGetter(async (hint?: StepUpHint) => {
      try {
        const token = await getAccessTokenWithPopup({
          authorizationParams: {
            audience: authConfig.audience,
            scope: authConfig.scope,
            ...(hint?.acr_values ? { acr_values: hint.acr_values } : {}),
            ...(typeof hint?.max_age === "number"
              ? { max_age: String(hint.max_age) }
              : {}),
          },
        });
        return token || null;
      } catch (err) {
        const code = (err as { error?: string })?.error;
        console.warn("getAccessTokenWithPopup failed: code=%s", code ?? "unknown");
        return null;
      }
    });
    return () => {
      setAccessTokenGetter(null);
      setStepUpTokenGetter(null);
    };
  }, [isAuthenticated, getAccessTokenSilently, getAccessTokenWithPopup]);

  return <>{children}</>;
}
