import { useState } from "react";

import { Wizard, type WizardStepDescriptor } from "@/components/common/Wizard";
import { EntityPicker } from "@/components/common/EntityPicker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { tenancyApi } from "@/lib/api/tenancy";

/**
 * Three-step user invite wizard.
 *
 *   1. Email & display name
 *   2. Scope chain + role
 *   3. Review & send (Entra B2B when MSAL is configured)
 */
const ROLES = ["viewer", "editor", "admin", "owner"] as const;
const SCOPE_KINDS = ["org", "team", "workspace", "project", "lab"] as const;

export function UserInviteWizard({
  defaultOrgId,
}: {
  defaultOrgId?: string;
}) {
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [orgId, setOrgId] = useState<string | null>(defaultOrgId ?? null);
  const [scopeKind, setScopeKind] = useState<(typeof SCOPE_KINDS)[number]>("org");
  const [scopeId, setScopeId] = useState<string | null>(null);
  const [role, setRole] = useState<(typeof ROLES)[number]>("viewer");
  const [sendB2B, setSendB2B] = useState(true);

  const steps: WizardStepDescriptor[] = [
    {
      id: "identity",
      title: "Email & display name",
      validate: () => /.+@.+\..+/.test(email),
      render: () => (
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Email</Label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label>Display name (optional)</Label>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
        </div>
      ),
    },
    {
      id: "scope",
      title: "Scope & role",
      validate: () => Boolean(orgId),
      render: () => (
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Organization</Label>
            <EntityPicker
              kind="organizations"
              value={orgId}
              onChange={(value) => setOrgId(value)}
            />
          </div>
          <div className="space-y-1">
            <Label>Scope kind</Label>
            <select
              className="w-full rounded-sm border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-1 font-mono text-sm"
              value={scopeKind}
              onChange={(e) => setScopeKind(e.target.value as (typeof SCOPE_KINDS)[number])}
            >
              {SCOPE_KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </div>
          {scopeKind !== "org" ? (
            <div className="space-y-1">
              <Label>Scope id</Label>
              <Input
                value={scopeId ?? ""}
                onChange={(e) => setScopeId(e.target.value || null)}
                placeholder="UUID of the team / workspace / project / lab"
                className="font-mono"
              />
            </div>
          ) : null}
          <div className="space-y-1">
            <Label>Role</Label>
            <select
              className="w-full rounded-sm border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-1 font-mono text-sm"
              value={role}
              onChange={(e) => setRole(e.target.value as (typeof ROLES)[number])}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
        </div>
      ),
    },
    {
      id: "review",
      title: "Review & send",
      render: () => (
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={sendB2B}
              onChange={(e) => setSendB2B(e.target.checked)}
            />
            Send Microsoft Entra B2B invitation (requires MSAL provider configured)
          </label>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-sm border border-[var(--border)] p-3 font-mono text-xs">
            {JSON.stringify(
              {
                email,
                display_name: displayName || null,
                org_id: orgId,
                scope_kind: scopeKind,
                scope_id: scopeId,
                role,
                send_entra_b2b_invitation: sendB2B,
              },
              null,
              2,
            )}
          </pre>
        </div>
      ),
    },
  ];

  const onFinish = async () => {
    if (!orgId) return;
    try {
      const result = await tenancyApi.invite({
        email,
        org_id: orgId,
        scope_kind: scopeKind,
        scope_id: scopeId ?? undefined,
        role,
        display_name: displayName || undefined,
        send_entra_b2b_invitation: sendB2B,
      });
      toast.success(
        `Invited ${email} (user_id=${result.user_id})`,
        result.entra_invitation
          ? { description: JSON.stringify(result.entra_invitation) }
          : undefined,
      );
    } catch (err) {
      toast.error("Invite failed", {
        description: err instanceof Error ? err.message : String(err),
      });
      throw err;
    }
  };

  return (
    <Wizard
      title="Invite user"
      subtitle="Creates a placeholder User + Membership, optionally mints an Entra B2B invitation."
      steps={steps}
      onFinish={onFinish}
    />
  );
}
