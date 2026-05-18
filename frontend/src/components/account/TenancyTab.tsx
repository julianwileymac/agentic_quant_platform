import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ConfirmFrictionDialog } from "@/components/auth/ConfirmFrictionDialog";
import { OrgSwitcher } from "@/components/onboarding/OrgSwitcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import { apiFetch } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";
import { toast } from "@/components/ui/toast";

interface MembershipRow {
  id: string;
  role: string | null;
}

interface DetailedMembership {
  id: string;
  scope_kind: string;
  scope_id: string;
  role: string | null;
}

interface WhoAmIResponse {
  id: string;
  email: string;
  display_name: string;
  auth_provider: string;
  auth_subject: string | null;
  avatar_url: string | null;
  workspaces: MembershipRow[];
  projects: MembershipRow[];
  labs: MembershipRow[];
  memberships?: DetailedMembership[];
  active_context: Record<string, unknown>;
}

interface OrgMembershipRow {
  id: string;
  name: string;
  role: string | null;
}

function MembershipBlock({ label, rows }: { label: string; rows: MembershipRow[] }) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-mono uppercase text-[var(--text-muted)]">{label}</div>
      {rows.length === 0 ? (
        <div className="text-xs text-[var(--text-muted)]">No {label.toLowerCase()}.</div>
      ) : (
        <ul className="space-y-1">
          {rows.map((row) => (
            <li
              key={row.id}
              className="flex items-center justify-between rounded border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-1 font-mono text-xs"
            >
              <span>{row.id}</span>
              <Badge variant="outline">{row.role ?? "viewer"}</Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function TenancyTab() {
  const queryClient = useQueryClient();
  const { claims } = useAuth();
  const [orgSwitcherOpen, setOrgSwitcherOpen] = useState(false);
  const [leaveTarget, setLeaveTarget] = useState<OrgMembershipRow | null>(null);

  const whoami = useApiQuery<WhoAmIResponse>({
    queryKey: ["auth", "whoami", "tenancy-tab"],
    path: "/auth/whoami",
  });

  const orgMemberships = useMemo<OrgMembershipRow[]>(() => {
    const rows =
      whoami.data?.memberships
        ?.filter((membership) => membership.scope_kind === "org")
        .map((membership) => ({
          id: membership.id,
          name: membership.scope_id,
          role: membership.role,
        })) ?? [];
    if (rows.length === 0 && claims.orgId) {
      rows.push({
        id: claims.orgId,
        name: claims.orgId,
        role: claims.roles[0] ?? "viewer",
      });
    }
    return rows;
  }, [claims.orgId, claims.roles, whoami.data?.memberships]);

  const leaveOrganization = async () => {
    if (!leaveTarget) return;
    try {
      await apiFetch(`/tenancy/memberships/${encodeURIComponent(leaveTarget.id)}`, {
        method: "DELETE",
      });
      await queryClient.invalidateQueries({ queryKey: ["auth", "whoami"] });
      toast.success(`Left organization ${leaveTarget.name}.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to leave organization.");
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Organizations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button type="button" variant="outline" onClick={() => setOrgSwitcherOpen(true)}>
            Active organization
          </Button>
          <div className="space-y-2">
            {orgMemberships.map((membership) => (
              <div
                key={membership.id}
                className="flex items-center justify-between rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2"
              >
                <div>
                  <div className="font-mono text-xs">{membership.name}</div>
                  <div className="text-xs text-[var(--text-secondary)]">
                    role: {membership.role ?? "viewer"}
                  </div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="border-[var(--neg-fg)] text-[var(--neg-fg)]"
                  onClick={() => setLeaveTarget(membership)}
                >
                  Leave organization
                </Button>
              </div>
            ))}
            {orgMemberships.length === 0 ? (
              <div className="text-xs text-[var(--text-secondary)]">No organization memberships.</div>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Memberships</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <MembershipBlock label="Workspaces" rows={whoami.data?.workspaces ?? []} />
          <MembershipBlock label="Projects" rows={whoami.data?.projects ?? []} />
          <MembershipBlock label="Labs" rows={whoami.data?.labs ?? []} />
        </CardContent>
      </Card>

      <OrgSwitcher open={orgSwitcherOpen} onOpenChange={setOrgSwitcherOpen} />

      <ConfirmFrictionDialog
        open={Boolean(leaveTarget)}
        onOpenChange={(open) => {
          if (!open) setLeaveTarget(null);
        }}
        title="Leave organization"
        description={`You will lose access to ${leaveTarget?.name ?? "this organization"} immediately.`}
        confirmationText={`leave ${leaveTarget?.name ?? ""}`}
        destructiveLabel="Leave organization"
        onConfirm={leaveOrganization}
      />
    </div>
  );
}
