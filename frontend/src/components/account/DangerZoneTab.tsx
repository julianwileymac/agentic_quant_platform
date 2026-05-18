import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ConfirmFrictionDialog } from "@/components/auth/ConfirmFrictionDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDeleteMeMutation, useMeProfileQuery } from "@/lib/api/me";
import { useAuth } from "@/lib/auth";
import { toast } from "@/components/ui/toast";

export function DangerZoneTab() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const profile = useMeProfileQuery();
  const deleteMe = useDeleteMeMutation();
  const [open, setOpen] = useState(false);

  const email = profile.data?.email ?? "";

  const handleDelete = async () => {
    if (!email) return;
    try {
      await deleteMe.mutateAsync({ confirmEmail: email });
      await logout();
      navigate("/auth/logout", { replace: true });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to delete account.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Danger Zone</CardTitle>
        <CardDescription>
          Deleting your account is irreversible and revokes access to all organizations.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button
          type="button"
          variant="destructive"
          onClick={() => setOpen(true)}
          disabled={!email || deleteMe.isPending}
        >
          Delete account
        </Button>

        <ConfirmFrictionDialog
          open={open}
          onOpenChange={setOpen}
          title="Delete account"
          description="This permanently deletes your account and ends your active sessions."
          confirmationText={email}
          confirmationLabel="Type your email to confirm"
          destructiveLabel="Delete my account"
          onConfirm={handleDelete}
        />
      </CardContent>
    </Card>
  );
}
