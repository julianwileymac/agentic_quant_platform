import { type ReactElement, useEffect } from "react";
import { useLocation } from "react-router-dom";

import { isAuthEnabled } from "./config";
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
