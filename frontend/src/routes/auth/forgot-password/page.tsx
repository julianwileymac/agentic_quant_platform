import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { isAuthEnabled, useAuth } from "@/lib/auth";

export function ForgotPasswordRoute() {
  const [params] = useSearchParams();
  const returnTo = params.get("return_to") || "/";
  const { enabled, isLoading, forgotPassword } = useAuth();

  useEffect(() => {
    if (!enabled || isLoading) return;
    void forgotPassword(returnTo);
  }, [enabled, forgotPassword, isLoading, returnTo]);

  if (!enabled && !isAuthEnabled()) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Password reset unavailable</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-[var(--text-secondary)]">
            This environment is running without an external identity provider.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Redirecting to password reset...</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-[var(--text-secondary)]">
          You will be returned once your password reset flow is complete.
        </CardContent>
      </Card>
    </div>
  );
}
