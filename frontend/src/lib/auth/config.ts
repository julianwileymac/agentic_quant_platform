/**
 * Frontend-side identity bootstrap configuration.
 *
 * Supports two backends (mirror of the backend's IdentityProvider
 * metaclass plumbing):
 *
 * - **MSAL / Microsoft Entra ID** (preferred for new deployments):
 *   `VITE_MSAL_TENANT_ID`, `VITE_MSAL_CLIENT_ID`, `VITE_MSAL_AUTHORITY`,
 *   `VITE_MSAL_REDIRECT_URI`, `VITE_MSAL_SCOPES`.
 * - **Auth0** (legacy fallback): `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`,
 *   `VITE_AUTH0_AUDIENCE`, `VITE_AUTH0_SCOPE`, `VITE_AUTH0_REDIRECT_URI`,
 *   `VITE_AUTH0_ORGANIZATION`.
 *
 * When MSAL is configured it takes precedence. When neither is
 * configured the SPA falls back to local-first mode (no IdP).
 *
 * The backend exposes `/auth/config` with the canonical values; the
 * frontend optionally fetches it at boot to surface a config-mismatch
 * warning when build-time env vars diverge.
 */

export type AuthProviderKind = "msal_entra" | "auth0" | "local";

export interface AuthConfig {
  enabled: boolean;
  required: boolean;
  provider: AuthProviderKind;
  // Common
  scope: string;
  redirectUri: string;
  // MSAL (provider = "msal_entra")
  msalTenantId: string;
  msalClientId: string;
  msalAuthority: string;
  // Auth0 (provider = "auth0") — kept for backwards compat
  domain: string;
  clientId: string;
  audience: string;
  organization: string | undefined;
}

function readEnv(key: string): string {
  const value = (import.meta.env as Record<string, string | undefined>)[key];
  return typeof value === "string" ? value.trim() : "";
}

function defaultRedirectUri(): string {
  if (typeof window === "undefined") return "";
  // Auth0 React's SPA quickstart recommends redirecting back to the
  // application origin. The SDK processes the code+state callback
  // before React Router renders, then `onRedirectCallback` restores
  // appState.returnTo. Keeping this at the origin avoids brittle
  // dashboard setup where `/auth/callback` is missing from Allowed
  // Callback URLs, and it works for both localhost and 127.0.0.1.
  return window.location.origin;
}

export const authConfig: AuthConfig = (() => {
  const requiredRaw = readEnv("VITE_AUTH_REQUIRED").toLowerCase();
  const required = requiredRaw ? !["0", "false", "no", "off"].includes(requiredRaw) : true;
  // MSAL configuration — preferred when all required pieces are set.
  const msalTenantId = readEnv("VITE_MSAL_TENANT_ID");
  const msalClientId = readEnv("VITE_MSAL_CLIENT_ID");
  const msalAuthority =
    readEnv("VITE_MSAL_AUTHORITY") ||
    (msalTenantId
      ? `https://login.microsoftonline.com/${msalTenantId}`
      : "https://login.microsoftonline.com/organizations");
  const msalScopes =
    readEnv("VITE_MSAL_SCOPES") ||
    "openid profile email offline_access User.Read";
  const msalRedirectUri = readEnv("VITE_MSAL_REDIRECT_URI") || defaultRedirectUri();

  // Auth0 configuration — fallback.
  const domain = readEnv("VITE_AUTH0_DOMAIN");
  const clientId = readEnv("VITE_AUTH0_CLIENT_ID");
  const audience = readEnv("VITE_AUTH0_AUDIENCE");
  const auth0Scope = readEnv("VITE_AUTH0_SCOPE") || "openid profile email offline_access";
  const auth0RedirectUri = readEnv("VITE_AUTH0_REDIRECT_URI") || defaultRedirectUri();
  const organization = readEnv("VITE_AUTH0_ORGANIZATION") || undefined;

  if (msalClientId) {
    return {
      enabled: true,
      required,
      provider: "msal_entra",
      scope: msalScopes,
      redirectUri: msalRedirectUri,
      msalTenantId,
      msalClientId,
      msalAuthority,
      domain: "",
      clientId: "",
      audience: "",
      organization: undefined,
    };
  }
  if (domain && clientId && audience) {
    return {
      enabled: true,
      required,
      provider: "auth0",
      scope: auth0Scope,
      redirectUri: auth0RedirectUri,
      msalTenantId: "",
      msalClientId: "",
      msalAuthority: "",
      domain,
      clientId,
      audience,
      organization,
    };
  }
  return {
    enabled: false,
    required,
    provider: "local",
    scope: "",
    redirectUri: defaultRedirectUri(),
    msalTenantId: "",
    msalClientId: "",
    msalAuthority: "",
    domain: "",
    clientId: "",
    audience: "",
    organization: undefined,
  };
})();

/**
 * True when the SPA build was given an IdP backend (MSAL or Auth0)
 * and should mount the matching Provider. Exposed as a function so
 * React components can branch on it without subscribing.
 */
export function isAuthEnabled(): boolean {
  return authConfig.enabled;
}

export function isAuthRequired(): boolean {
  return authConfig.required;
}

/**
 * Return the active provider kind so callers can branch (e.g. the
 * AuthProvider component picks between `<MsalProvider>` and
 * `<Auth0Provider>`).
 */
export function activeAuthProvider(): AuthProviderKind {
  return authConfig.provider;
}
