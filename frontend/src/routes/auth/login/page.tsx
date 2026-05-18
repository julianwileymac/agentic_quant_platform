import { ShieldCheck } from "lucide-react";
import { useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { GoogleButton } from "@/components/auth/GoogleButton";
import { MicrosoftButton } from "@/components/auth/MicrosoftButton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { authConfig, isAuthEnabled, isAuthRequired, useAuth } from "@/lib/auth";

/**
 * Login route.
 *
 * In local-first mode (`VITE_AUTH0_DOMAIN` unset) the route renders an
 * informational notice instead of pretending to log in.
 */
export function LoginRoute() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = params.get("return_to") || "/";
  const { enabled, isLoading, isAuthenticated, loginWithRedirect, loginWithMicrosoft, loginWithGoogle } =
    useAuth();
  const brandName =
    ((import.meta.env as Record<string, string | undefined>).VITE_AUTH0_BRAND_NAME ?? "").trim() ||
    "Agentic Quant Platform";
  const logoUrl =
    ((import.meta.env as Record<string, string | undefined>).VITE_AUTH0_BRAND_LOGO_URL ?? "").trim() ||
    null;
  const googleConnection =
    ((import.meta.env as Record<string, string | undefined>).VITE_AUTH0_GOOGLE_CONNECTION ?? "").trim();
  const showGoogle = googleConnection.length > 0;

  useEffect(() => {
    if (!enabled) return;
    if (isLoading) return;
    if (!isAuthenticated) return;
    navigate(returnTo, { replace: true });
  }, [enabled, isAuthenticated, isLoading, navigate, returnTo]);

  if (!enabled) {
    return isAuthRequired() ? <AuthRequiredConfigNotice /> : <LocalModeNotice />;
  }

  const withReturnTo = (path: string) => `${path}?return_to=${encodeURIComponent(returnTo)}`;

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-app)] p-6">
      <Card className="w-full max-w-md">
        <CardHeader className="border-b-0 pb-2">
          <CardTitle className="flex flex-col items-center gap-2 text-center text-lg">
            {logoUrl ? (
              <img src={logoUrl} alt={brandName} className="h-10 w-auto max-w-[180px] object-contain" />
            ) : (
              <ShieldCheck className="size-8 text-[var(--info-fg)]" />
            )}
            <span>{brandName}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button
            type="button"
            className="w-full"
            onClick={() => {
              void loginWithRedirect(returnTo);
            }}
            disabled={isLoading}
          >
            Continue with Email
          </Button>

          <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
            <div className="h-px flex-1 bg-[var(--border-default)]" />
            <span>or</span>
            <div className="h-px flex-1 bg-[var(--border-default)]" />
          </div>

          <MicrosoftButton
            onClick={() => loginWithMicrosoft(returnTo)}
            disabled={isLoading}
            className="w-full"
          />

          {showGoogle ? (
            <GoogleButton
              onClick={() => loginWithGoogle(returnTo)}
              disabled={isLoading}
              className="w-full"
            />
          ) : null}

          <div className="space-y-1 pt-2 text-center text-sm text-[var(--text-secondary)]">
            <div>
              New here?{" "}
              <Link className="text-[var(--info-fg)] hover:underline" to={withReturnTo("/auth/signup")}>
                Create an account
              </Link>
            </div>
            <div>
              <Link
                className="text-[var(--info-fg)] hover:underline"
                to={withReturnTo("/auth/forgot-password")}
              >
                Forgot password?
              </Link>
            </div>
            <div className="pt-2 text-xs">
              <a className="hover:underline" href="/legal/terms">
                Terms
              </a>{" "}
              ·{" "}
              <a className="hover:underline" href="/legal/privacy">
                Privacy
              </a>
            </div>
          </div>
        </CardContent>
      </Card>
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
            This deployment is running with <code>AQP_AUTH_PROVIDER=local</code>, so there is
            no identity provider to redirect to. Every request is automatically served as the
            deterministic <code>default-user</code>.
          </p>
          <p style={{ fontSize: 14, lineHeight: 1.55 }}>
            To enable Auth0 + Google sign-in, set the SPA build environment variables{" "}
            <code>VITE_AUTH0_DOMAIN</code>, <code>VITE_AUTH0_CLIENT_ID</code>, and{" "}
            <code>VITE_AUTH0_AUDIENCE</code>, and configure the matching
            <code>AQP_AUTH_*</code> values on the API server.
          </p>
        </div>
      </div>
    );
  }
  return null;
}

function AuthRequiredConfigNotice() {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Authentication configuration required</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-[var(--text-secondary)]">
          <p>
            This AQP deployment requires authentication before the control plane can
            load, but no Auth0/MSAL frontend configuration was provided.
          </p>
          <p>
            Configure Auth0 with <code>VITE_AUTH0_DOMAIN</code>,{" "}
            <code>VITE_AUTH0_CLIENT_ID</code>, and <code>VITE_AUTH0_AUDIENCE</code>,
            or explicitly opt out for local-only development with{" "}
            <code>VITE_AUTH_REQUIRED=false</code>.
          </p>
          <p className="text-xs">
            Current provider: <code>{authConfig.provider}</code>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
