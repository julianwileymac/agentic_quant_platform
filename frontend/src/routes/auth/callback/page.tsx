import { useEffect } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "@/lib/auth";

/**
 * Auth0 redirect callback route.
 *
 * The `<Auth0Provider>` already handles the authorization-code +
 * PKCE exchange via its `onRedirectCallback` hook, which calls
 * `window.history.replaceState` with the `appState.returnTo` target.
 * That means by the time React mounts this component the URL has
 * usually already been rewritten — so we just guide the user to the
 * dashboard if they happen to land here directly.
 */
export function CallbackRoute() {
  const { enabled, isLoading, isAuthenticated } = useAuth();

  useEffect(() => {
    if (!enabled) return;
    if (isLoading || !isAuthenticated) return;
    if (typeof window !== "undefined" && window.location.pathname === "/auth/callback") {
      window.history.replaceState({}, document.title, "/");
    }
  }, [enabled, isLoading, isAuthenticated]);

  if (!enabled || (!isLoading && isAuthenticated)) {
    return <Navigate to="/" replace />;
  }
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
      <span>Finalising sign-in…</span>
    </div>
  );
}
