import { useState } from "react";

import { MfaEnrollDialog } from "@/components/auth/MfaEnrollDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  meKeys,
  useChangePasswordMutation,
  useDeleteMfaFactorMutation,
  useMeAuditQuery,
  useMfaFactorsQuery,
} from "@/lib/api/me";
import { toast } from "@/components/ui/toast";
import { useQueryClient } from "@tanstack/react-query";

type EnrollFactor = "totp" | "sms" | "webauthn-roaming" | "webauthn-platform";

const ENROLL_FACTORS: EnrollFactor[] = [
  "totp",
  "sms",
  "webauthn-roaming",
  "webauthn-platform",
];

function PasswordChangeCard() {
  const changePassword = useChangePasswordMutation();

  const handleChangePassword = async () => {
    try {
      const data = await changePassword.mutateAsync({});
      window.open(data.ticket_url, "_blank", "noopener,noreferrer");
      toast.success("Password reset flow opened in a new tab.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to start password reset.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Password</CardTitle>
      </CardHeader>
      <CardContent>
        <Button
          type="button"
          onClick={() => void handleChangePassword()}
          disabled={changePassword.isPending}
        >
          {changePassword.isPending ? "Preparing..." : "Change password"}
        </Button>
      </CardContent>
    </Card>
  );
}

function MfaFactorsCard() {
  const queryClient = useQueryClient();
  const factors = useMfaFactorsQuery();
  const deleteFactor = useDeleteMfaFactorMutation();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedFactor, setSelectedFactor] = useState<EnrollFactor>("totp");

  const handleRemove = async (id: string) => {
    try {
      await deleteFactor.mutateAsync({ id });
      await queryClient.invalidateQueries({ queryKey: meKeys.mfaFactors });
      toast.success("MFA factor removed.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to remove MFA factor.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>MFA factors</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="overflow-x-auto rounded-md border border-[var(--border-default)]">
          <table className="w-full text-left text-sm">
            <thead className="bg-[var(--bg-elevated)] text-xs uppercase text-[var(--text-secondary)]">
              <tr>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Enrolled</th>
                <th className="px-3 py-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {(factors.data ?? []).map((factor) => (
                <tr key={factor.id} className="border-t border-[var(--border-subtle)]">
                  <td className="px-3 py-2">
                    <Badge variant="outline">{factor.type}</Badge>
                  </td>
                  <td className="px-3 py-2">{factor.name ?? "Unnamed factor"}</td>
                  <td className="px-3 py-2 text-xs text-[var(--text-secondary)]">
                    {new Date(factor.enrolled_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => void handleRemove(factor.id)}
                      className="border-[var(--neg-fg)] text-[var(--neg-fg)]"
                    >
                      Remove
                    </Button>
                  </td>
                </tr>
              ))}
              {(factors.data ?? []).length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-3 py-3 text-xs text-[var(--text-secondary)]">
                    No MFA factors enrolled yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedFactor}
            onChange={(event) => setSelectedFactor(event.target.value as EnrollFactor)}
            className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
          >
            {ENROLL_FACTORS.map((factor) => (
              <option key={factor} value={factor}>
                {factor}
              </option>
            ))}
          </select>
          <Button type="button" onClick={() => setDialogOpen(true)}>
            Add factor
          </Button>
        </div>

        <MfaEnrollDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          factor={selectedFactor}
          onComplete={() => {
            void queryClient.invalidateQueries({ queryKey: meKeys.mfaFactors });
          }}
        />
      </CardContent>
    </Card>
  );
}

function RecentActivityCard() {
  const activity = useMeAuditQuery(10, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent activity</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {(activity.data?.events ?? []).map((event) => (
          <div
            key={event.id}
            className="rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-xs"
          >
            <div className="font-medium">{event.event_type}</div>
            <div className="text-[var(--text-secondary)]">
              {new Date(event.date).toLocaleString()} · {event.ip ?? "unknown IP"} ·{" "}
              {event.connection ?? "no connection"}
            </div>
          </div>
        ))}
        {(activity.data?.events ?? []).length === 0 ? (
          <div className="text-xs text-[var(--text-secondary)]">No recent events.</div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function SecurityTab() {
  return (
    <div className="space-y-4">
      <PasswordChangeCard />
      <MfaFactorsCard />
      <RecentActivityCard />
    </div>
  );
}
