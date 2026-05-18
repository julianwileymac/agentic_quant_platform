import { AlertTriangle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type InviteAcceptStatus = "loading" | "success" | "failure";

interface InviteAcceptScreenProps {
  status: InviteAcceptStatus;
  orgName?: string | null;
  redirectUrl?: string | null;
  onContinue?: () => void;
}

export function InviteAcceptScreen({
  status,
  orgName,
  redirectUrl,
  onContinue,
}: InviteAcceptScreenProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-app)] p-6">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Invitation</CardTitle>
          {status === "loading" ? (
            <CardDescription>Validating your organization invite.</CardDescription>
          ) : null}
          {status === "success" ? (
            <CardDescription>
              Your invite was accepted. Continue to finish account setup.
            </CardDescription>
          ) : null}
          {status === "failure" ? (
            <CardDescription>
              This invite is no longer valid. Ask your administrator for a new invitation.
            </CardDescription>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-4">
          {status === "loading" ? (
            <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
              <Loader2 className="size-4 animate-spin" />
              Accepting invitation...
            </div>
          ) : null}

          {status === "success" ? (
            <div className="space-y-3">
              <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 text-sm">
                Welcome to {orgName ?? "your organization"}!
              </div>
              <Button type="button" className="w-full" onClick={onContinue}>
                Continue to sign up
              </Button>
              {redirectUrl ? (
                <div className="truncate text-xs text-[var(--text-secondary)]">{redirectUrl}</div>
              ) : null}
            </div>
          ) : null}

          {status === "failure" ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 rounded-md border border-[var(--warn-fg)]/40 bg-[var(--warn-bg)] p-3 text-sm text-[var(--warn-fg)]">
                <AlertTriangle className="size-4" />
                This invite is invalid or expired.
              </div>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => {
                  window.location.href = "mailto:admin@aqp.local";
                }}
              >
                Contact your administrator
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
