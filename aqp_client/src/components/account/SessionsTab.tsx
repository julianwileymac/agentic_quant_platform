import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ConfirmFrictionDialog } from "@/components/auth/ConfirmFrictionDialog";
import { SessionRow } from "@/components/auth/SessionRow";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { meKeys, useRevokeAllSessionsMutation, useRevokeSessionMutation, useSessionsQuery } from "@/lib/api/me";
import { toast } from "@/components/ui/toast";

export function SessionsTab() {
  const queryClient = useQueryClient();
  const sessionsQuery = useSessionsQuery();
  const revokeSession = useRevokeSessionMutation();
  const revokeAll = useRevokeAllSessionsMutation();
  const [confirmGlobal, setConfirmGlobal] = useState(false);

  const browserAgent = useMemo(
    () => (typeof navigator !== "undefined" ? navigator.userAgent : ""),
    [],
  );

  const handleRevoke = async (id: string) => {
    try {
      await revokeSession.mutateAsync({ id });
      await queryClient.invalidateQueries({ queryKey: meKeys.sessions });
      toast.success("Session revoked.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to revoke session.");
    }
  };

  const handleRevokeAll = async () => {
    try {
      const result = await revokeAll.mutateAsync({});
      await queryClient.invalidateQueries({ queryKey: meKeys.sessions });
      toast.success(`Signed out ${result.revoked} sessions.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to sign out all sessions.");
    }
  };

  const sessions = sessionsQuery.data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sessions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {sessions.map((session, index) => {
          const isCurrent = session.user_agent
            ? session.user_agent === browserAgent
            : index === 0;
          return (
            <SessionRow
              key={session.id}
              session={session}
              isCurrent={isCurrent}
              onRevoke={() => handleRevoke(session.id)}
            />
          );
        })}

        {sessions.length === 0 ? (
          <div className="text-sm text-[var(--text-secondary)]">No active sessions found.</div>
        ) : null}

        <div className="sticky bottom-0 flex justify-end border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] pt-3">
          <Button type="button" variant="destructive" onClick={() => setConfirmGlobal(true)}>
            Sign out everywhere
          </Button>
        </div>

        <ConfirmFrictionDialog
          open={confirmGlobal}
          onOpenChange={setConfirmGlobal}
          title="Sign out all sessions"
          description="This will revoke every session, including your current browser session."
          confirmationText="sign out everywhere"
          destructiveLabel="Sign out everywhere"
          onConfirm={handleRevokeAll}
        />
      </CardContent>
    </Card>
  );
}
