import { useEffect } from "react";
import { Navigate } from "react-router-dom";
import { Loader2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    <div className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Finalizing sign-in...</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <Loader2 className="size-4 animate-spin" />
          Completing callback flow
        </CardContent>
      </Card>
    </div>
  );
}
