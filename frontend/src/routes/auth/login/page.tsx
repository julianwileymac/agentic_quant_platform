import { useEffect } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { isAuthEnabled, useAuth } from "@/lib/auth";

/**
 * Login route. Redirects authenticated users back to the dashboard
 * (honouring the `?return_to=` query string) and triggers the IdP
 * Universal Login redirect for everyone else.
 *
 * In local-first mode (`VITE_AUTH0_DOMAIN` unset) the route renders an
 * informational notice instead of pretending to log in.
 */
export function LoginRoute() {
  const [params] = useSearchParams();
  const returnTo = params.get("return_to") || "/";
  const { enabled, isLoading, isAuthenticated, loginWithRedirect } = useAuth();

  useEffect(() => {
    if (!enabled) return;
    if (isLoading) return;
    if (isAuthenticated) return;
    void loginWithRedirect(returnTo);
  }, [enabled, isLoading, isAuthenticated, loginWithRedirect, returnTo]);

  if (!enabled) {
    return <LocalModeNotice />;
  }
  if (isAuthenticated && !isLoading) {
    return <Navigate to={returnTo} replace />;
  }
  return <LoginSplash />;
}

function LoginSplash() {
  return (
    <div
      role="status"
      aria-busy="true"
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily:
          "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        color: "var(--text-secondary, #444)",
      }}
    >
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 18, fontWeight: 600 }}>Redirecting to identity provider…</div>
        <div style={{ fontSize: 13, marginTop: 8, color: "var(--text-muted, #888)" }}>
          You'll be returned here once you sign in.
        </div>
      </div>
    </div>
  );
}

function LocalModeNotice() {
  if (!isAuthEnabled()) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 32,
        }}
      >
        <div
          style={{
            maxWidth: 540,
            border: "1px solid var(--border-strong, #ddd)",
            borderRadius: 8,
            padding: 24,
            background: "var(--bg-elevated, #fff)",
          }}
        >
          <h1 style={{ marginTop: 0, fontSize: 18 }}>Local-first mode</h1>
          <p style={{ fontSize: 14, lineHeight: 1.55 }}>
            This deployment is running with <code>AQP_AUTH_PROVIDER=local</code>, so there
            is no identity provider to redirect to. Every request is automatically
            served as the deterministic <code>default-user</code>.
          </p>
          <p style={{ fontSize: 14, lineHeight: 1.55 }}>
            To enable Auth0 + Google sign-in, set the SPA build environment
            variables <code>VITE_AUTH0_DOMAIN</code>, <code>VITE_AUTH0_CLIENT_ID</code>,
            and <code>VITE_AUTH0_AUDIENCE</code>, and configure the matching
            <code>AQP_AUTH_*</code> values on the API server.
          </p>
        </div>
      </div>
    );
  }
  return null;
}
