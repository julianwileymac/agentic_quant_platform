import {
  EventType,
  type AuthenticationResult,
  type Configuration,
  PublicClientApplication,
  type SilentRequest,
} from "@azure/msal-browser";
import { MsalProvider as InnerMsalProvider, useMsal } from "@azure/msal-react";
import { type ReactNode, useEffect, useMemo } from "react";

import { authConfig } from "./config";
import { setAccessTokenGetter, setStepUpTokenGetter, type StepUpHint } from "./tokenStore";

/**
 * MSAL / Entra ID branch of the Vite frontend's auth bootstrap.
 *
 * Per the 2026 multi-IdP pattern documented in
 * `aqp_docs/multi-tenancy.md`, MSAL is preferred when `VITE_MSAL_*` env
 * vars are present; the AuthProvider component picks this branch over
 * `<Auth0Provider>` automatically.
 *
 * The companion `public/redirect.html` file is required by MSAL v5 —
 * Vite builds copy it verbatim to the dist so the redirect handler
 * lives at a stable, dependency-free URL.
 */

function buildPca(): PublicClientApplication {
  const config: Configuration = {
    auth: {
      clientId: authConfig.msalClientId,
      authority: authConfig.msalAuthority,
      redirectUri: `${window.location.origin}/redirect.html`,
      postLogoutRedirectUri: window.location.origin,
      navigateToLoginRequestUrl: true,
    },
    cache: {
      // Session storage keeps tokens out of long-lived browser
      // localStorage. The BFF flow (POST /auth/refresh on the AQP API)
      // is the canonical refresh path; MSAL holds nothing persistent.
      cacheLocation: "sessionStorage",
      storeAuthStateInCookie: false,
    },
    system: {
      windowHashTimeout: 60_000,
      iframeHashTimeout: 10_000,
      loadFrameTimeout: 10_000,
    },
  };
  const pca = new PublicClientApplication(config);
  // Surface the initially-cached account, if any, so other consumers
  // of the PCA see a non-null .getActiveAccount() right after boot.
  pca.addEventCallback((event) => {
    if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
      const result = event.payload as AuthenticationResult;
      if (result.account) {
        pca.setActiveAccount(result.account);
      }
    }
  });
  return pca;
}

export function MsalProvider({ children }: { children: ReactNode }) {
  const pca = useMemo(buildPca, []);

  return (
    <InnerMsalProvider instance={pca}>
      <MsalTokenStoreBinder>{children}</MsalTokenStoreBinder>
    </InnerMsalProvider>
  );
}

function MsalTokenStoreBinder({ children }: { children: ReactNode }) {
  const { instance, accounts } = useMsal();
  const scopes = authConfig.scope
    .split(/\s+/)
    .map((s) => s.trim())
    .filter(Boolean);

  useEffect(() => {
    const account = accounts[0] ?? null;
    if (!account) {
      setAccessTokenGetter(null);
      setStepUpTokenGetter(null);
      return;
    }
    instance.setActiveAccount(account);
    setAccessTokenGetter(async () => {
      const request: SilentRequest = {
        account,
        scopes,
      };
      try {
        const result = await instance.acquireTokenSilent(request);
        return result.accessToken || null;
      } catch (err) {
        // Per MSAL guidance, fall back to redirect for interaction-
        // required errors. We DO NOT log the underlying token value;
        // the error object only carries a status code + message.
        try {
          await instance.acquireTokenRedirect(request);
        } catch {
          /* surfaces as a 401 + RequireAuth redirect */
        }
        return null;
      }
    });
    // Step-up via popup so the destructive operation can resume
    // without a full redirect roundtrip. Entra honours the OIDC
    // ``claims`` parameter for ACR enforcement; we request the
    // standard MFA reference (``c1``) so the user must complete an
    // MFA factor regardless of the existing session age.
    setStepUpTokenGetter(async (hint?: StepUpHint) => {
      // The hint.acr_values is the canonical OpenID Connect URI; for
      // Entra we translate it to the ``claims`` parameter shape.
      const claimsBody = hint?.acr_values
        ? JSON.stringify({
            id_token: {
              acr: { essential: true, values: ["c1"] },
            },
          })
        : undefined;
      try {
        const result = await instance.acquireTokenPopup({
          account,
          scopes,
          prompt: "login",
          ...(claimsBody ? { claims: claimsBody } : {}),
          ...(typeof hint?.max_age === "number"
            ? { extraQueryParameters: { max_age: String(hint.max_age) } }
            : {}),
        });
        return result.accessToken || null;
      } catch (err) {
        // Most common: user closed the popup or browser blocked it.
        // Surface as null so the caller can show a "MFA required"
        // toast — never echo the raw error to console.
        return null;
      }
    });
    return () => {
      setAccessTokenGetter(null);
      setStepUpTokenGetter(null);
    };
  }, [instance, accounts, scopes]);

  return <>{children}</>;
}
