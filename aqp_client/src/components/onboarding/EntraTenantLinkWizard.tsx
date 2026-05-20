import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { EntityPicker } from "@/components/common/EntityPicker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useApiQuery } from "@/lib/api/hooks";
import { apiFetch } from "@/lib/api/client";
import { toast } from "@/components/ui/toast";

interface PendingEntraTenantLink {
  id: string;
  entra_tenant_id: string;
  primary_domain: string | null;
  first_seen_user_email: string | null;
  display_name: string | null;
  created_at: string | null;
}

interface PendingResponse {
  items: PendingEntraTenantLink[];
  total: number;
}

const ROLE_OPTIONS = ["viewer", "editor", "admin", "owner"] as const;

export function EntraTenantLinkWizard() {
  const [selectedLinkId, setSelectedLinkId] = useState<string | null>(null);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [defaultRole, setDefaultRole] = useState<(typeof ROLE_OPTIONS)[number]>("viewer");

  const pending = useApiQuery<PendingResponse>({
    queryKey: ["tenancy", "entra-links", "pending"],
    path: "/tenancy/entra-links",
    query: { status: "pending" },
    select: (raw) => raw as PendingResponse,
  });

  const links = pending.data?.items ?? [];
  const selectedLink = useMemo(
    () => links.find((item) => item.id === selectedLinkId) ?? null,
    [links, selectedLinkId],
  );

  const promoteMutation = useMutation({
    mutationFn: async (payload: { id: string; organization_id: string; default_role: string }) =>
      apiFetch(`/tenancy/entra-links/${encodeURIComponent(payload.id)}/promote`, {
        method: "POST",
        body: JSON.stringify({
          organization_id: payload.organization_id,
          default_role: payload.default_role,
        }),
      }),
    onSuccess: () => {
      toast.success("Tenant link promoted.");
      pending.refetch();
      setSelectedLinkId(null);
      setSelectedOrgId(null);
      setDefaultRole("viewer");
    },
    onError: (error) => {
      toast.error("Failed to promote tenant link", {
        description: error instanceof Error ? error.message : String(error),
      });
    },
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Step 1: Detect pending Entra links</CardTitle>
          <CardDescription>
            Review tenant IDs discovered from first-login claims that require super-admin promotion.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {pending.isPending ? (
            <div className="text-sm text-[var(--text-secondary)]">Loading pending links...</div>
          ) : null}
          {!pending.isPending && links.length === 0 ? (
            <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 text-sm text-[var(--text-secondary)]">
              No pending tenant links right now.
            </div>
          ) : null}
          {links.map((row) => (
            <button
              type="button"
              key={row.id}
              onClick={() => setSelectedLinkId(row.id)}
              className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 text-left data-[active=true]:border-[var(--info-fg)]"
              data-active={selectedLinkId === row.id}
            >
              <div className="font-mono text-xs">{row.entra_tenant_id}</div>
              <div className="text-xs text-[var(--text-secondary)]">
                {row.primary_domain ?? "No primary domain"}
              </div>
              <div className="text-xs text-[var(--text-secondary)]">
                first seen: {row.first_seen_user_email ?? "unknown"}
              </div>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Step 2: Choose organization and default role</CardTitle>
          <CardDescription>
            Map the selected Entra tenant to an existing organization, then set its bootstrap role.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label>Organization</Label>
            <EntityPicker
              kind="organizations"
              value={selectedOrgId}
              onChange={(value) => setSelectedOrgId(value)}
              placeholder="Select organization"
            />
          </div>
          <div className="space-y-1">
            <Label>Default role</Label>
            <select
              value={defaultRole}
              onChange={(event) =>
                setDefaultRole(event.target.value as (typeof ROLE_OPTIONS)[number])
              }
              className="h-9 w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Step 3: Confirm promotion</CardTitle>
          <CardDescription>
            Promote the pending row to activate organization mapping for future sign-ins.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <pre className="rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 font-mono text-xs">
            {JSON.stringify(
              {
                pending_link_id: selectedLink?.id ?? null,
                entra_tenant_id: selectedLink?.entra_tenant_id ?? null,
                organization_id: selectedOrgId,
                default_role: defaultRole,
              },
              null,
              2,
            )}
          </pre>
          <Button
            type="button"
            disabled={!selectedLink?.id || !selectedOrgId || promoteMutation.isPending}
            onClick={() => {
              if (!selectedLink?.id || !selectedOrgId) return;
              promoteMutation.mutate({
                id: selectedLink.id,
                organization_id: selectedOrgId,
                default_role: defaultRole,
              });
            }}
          >
            {promoteMutation.isPending ? "Promoting..." : "Promote tenant link"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
