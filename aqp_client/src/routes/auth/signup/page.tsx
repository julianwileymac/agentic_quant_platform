import { ShieldCheck } from "lucide-react";
import { useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { GoogleButton } from "@/components/auth/GoogleButton";
import { MicrosoftButton } from "@/components/auth/MicrosoftButton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { isAuthEnabled, useAuth } from "@/lib/auth";

export function SignupRoute() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = params.get("return_to") || "/";
  const {
    enabled,
    isLoading,
    isAuthenticated,
    signupWithRedirect,
    loginWithMicrosoft,
    loginWithGoogle,
  } = useAuth();

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
    if (!enabled || isLoading || isAuthenticated) return;
    void signupWithRedirect(returnTo);
  }, [enabled, isAuthenticated, isLoading, returnTo, signupWithRedirect]);

  useEffect(() => {
    if (!enabled || isLoading || !isAuthenticated) return;
    navigate(returnTo, { replace: true });
  }, [enabled, isAuthenticated, isLoading, navigate, returnTo]);

  if (!enabled) return <LocalModeNotice />;

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
              void signupWithRedirect(returnTo);
            }}
            disabled={isLoading}
          >
            Sign up with Email
          </Button>

          <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
            <div className="h-px flex-1 bg-[var(--border-default)]" />
            <span>or</span>
            <div className="h-px flex-1 bg-[var(--border-default)]" />
          </div>

          <MicrosoftButton onClick={() => loginWithMicrosoft(returnTo)} variant="signup" />
          {showGoogle ? (
            <GoogleButton onClick={() => loginWithGoogle(returnTo)} variant="signup" />
          ) : null}

          <div className="space-y-1 pt-2 text-center text-sm text-[var(--text-secondary)]">
            <div>
              Already have an account?{" "}
              <Link className="text-[var(--info-fg)] hover:underline" to={withReturnTo("/auth/login")}>
                Sign in
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
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function LocalModeNotice() {
  if (!isAuthEnabled()) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <Card className="w-full max-w-lg">
          <CardHeader>
            <CardTitle>Local-first mode</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-[var(--text-secondary)]">
            Sign-up redirect is unavailable because the SPA is running in local auth bypass mode.
          </CardContent>
        </Card>
      </div>
    );
  }
  return null;
}
