import { type ReactElement, useEffect } from "react";
import { useLocation } from "react-router-dom";

import { isAuthEnabled, isAuthRequired } from "./config";
import { useAuth } from "./useAuth";

/**
 * Route guard that redirects unauthenticated users to the IdP login
 * page, preserving the original destination so post-login redirect
 * lands them where they were headed.
 *
 * In local-first deployments the guard is a no-op — the deterministic
 * default user is always considered authenticated and the page renders
 * directly. This keeps the authoring story for new routes consistent
 * across modes: wrap with `<RequireAuth>` and forget about it.
 */
export function RequireAuth({ children }: { children: ReactElement }): ReactElement {
  const location = useLocation();
  const { enabled, isLoading, isAuthenticated, loginWithRedirect } = useAuth();

  useEffect(() => {
    if (!enabled) return;
    if (isLoading) return;
    if (isAuthenticated) return;
    void loginWithRedirect(location.pathname + location.search);
  }, [enabled, isLoading, isAuthenticated, loginWithRedirect, location.pathname, location.search]);

  if (!enabled && isAuthRequired()) {
    return <AuthConfigurationRequiredScreen />;
  }
  if (!enabled) {
    return children;
  }
  if (isLoading || !isAuthenticated) {
    return <AuthLoadingScreen />;
  }
  return children;
}

function AuthLoadingScreen() {
  if (!isAuthEnabled()) return null;
  return (
    <div
      role="status"
      aria-busy="true"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        fontSize: "14px",
        color: "var(--text-muted, #888)",
        fontFamily:
          "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      <span>Authenticating with your identity provider…</span>
    </div>
  );
}

function AuthConfigurationRequiredScreen() {
  return (
    <div
      role="alert"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        padding: 32,
        fontFamily:
          "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      <div
        style={{
          maxWidth: 560,
          border: "1px solid var(--border-strong, #ddd)",
          borderRadius: 8,
          padding: 24,
          background: "var(--bg-elevated, #fff)",
        }}
      >
        <h1 style={{ marginTop: 0, fontSize: 18 }}>Authentication is required</h1>
        <p style={{ fontSize: 14, lineHeight: 1.55 }}>
          This cluster build requires Auth0/MSAL authentication, but the frontend
          was not given identity-provider configuration. Set{" "}
          <code>VITE_AUTH0_DOMAIN</code>, <code>VITE_AUTH0_CLIENT_ID</code>, and{" "}
          <code>VITE_AUTH0_AUDIENCE</code> (or the MSAL equivalents), then rebuild
          the frontend.
        </p>
        <p style={{ fontSize: 13, lineHeight: 1.55, color: "var(--text-muted, #777)" }}>
          Local development can opt out explicitly with <code>VITE_AUTH_REQUIRED=false</code>{" "}
          and <code>AQP_AUTH_PROVIDER=local</code>.
        </p>
      </div>
    </div>
  );
}
