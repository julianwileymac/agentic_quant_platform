import { useState } from "react";

import { Wizard, type WizardStepDescriptor } from "@/components/common/Wizard";
import { EntityPicker } from "@/components/common/EntityPicker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { tenancyApi } from "@/lib/api/tenancy";

/**
 * Five-step Entra tenant link wizard.
 *
 *   1. Choose AQP organization
 *   2. Entra tenant ID + primary domain
 *   3. Allowed email domains (CSV)
 *   4. App-role mapping
 *   5. Test sign-in (preview the link payload)
 */
export function EntraTenantLinkWizard({
  onCreated,
}: {
  onCreated?: (link: { id: string; status: string }) => void;
}) {
  const [orgId, setOrgId] = useState<string | null>(null);
  const [tid, setTid] = useState("");
  const [primaryDomain, setPrimaryDomain] = useState("");
  const [allowedDomains, setAllowedDomains] = useState("");
  const [roleMapping, setRoleMapping] = useState(
    JSON.stringify(
      {
        "aqp.admin": "admin",
        "aqp.editor": "editor",
        "aqp.viewer": "viewer",
        "aqp.terraform.operator": "editor",
        "aqp.terraform.approver": "admin",
      },
      null,
      2,
    ),
  );
  const [activate, setActivate] = useState(true);

  const steps: WizardStepDescriptor[] = [
    {
      id: "org",
      title: "Choose organization",
      validate: () => Boolean(orgId),
      render: () => (
        <div className="space-y-1">
          <Label>Target AQP organization</Label>
          <EntityPicker
            kind="organizations"
            value={orgId}
            onChange={(value) => setOrgId(value)}
            placeholder="Select organization"
          />
        </div>
      ),
    },
    {
      id: "tenant",
      title: "Entra tenant",
      validate: () => tid.trim().length >= 8,
      render: () => (
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Entra tenant ID (tid)</Label>
            <Input
              value={tid}
              onChange={(e) => setTid(e.target.value)}
              placeholder="11111111-2222-3333-4444-555555555555"
              className="font-mono"
            />
          </div>
          <div className="space-y-1">
            <Label>Primary domain</Label>
            <Input
              value={primaryDomain}
              onChange={(e) => setPrimaryDomain(e.target.value)}
              placeholder="wiley.tech"
            />
          </div>
        </div>
      ),
    },
    {
      id: "domains",
      title: "Allowed email domains",
      optional: true,
      render: () => (
        <div className="space-y-1">
          <Label>Allowed email domains (CSV)</Label>
          <Input
            value={allowedDomains}
            onChange={(e) => setAllowedDomains(e.target.value)}
            placeholder="wiley.tech, julianwiley.com"
          />
          <p className="text-xs text-[var(--text-secondary)]">
            Leave empty to allow any email from the tenant.
          </p>
        </div>
      ),
    },
    {
      id: "role-mapping",
      title: "App-role mapping",
      render: () => (
        <div className="space-y-1">
          <Label>Role mapping (JSON)</Label>
          <textarea
            className="h-48 w-full resize-none rounded-sm border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-2 font-mono text-xs"
            value={roleMapping}
            onChange={(e) => setRoleMapping(e.target.value)}
          />
          <p className="text-xs text-[var(--text-secondary)]">
            Maps Entra app-role names (e.g. <code>aqp.admin</code>) to AQP
            role lattice (viewer / editor / admin / owner).
          </p>
        </div>
      ),
    },
    {
      id: "review",
      title: "Review & link",
      render: () => (
        <div className="space-y-3 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={activate}
              onChange={(e) => setActivate(e.target.checked)}
            />
            Activate link immediately (otherwise creates a <code>pending</code> link)
          </label>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-sm border border-[var(--border)] p-3 font-mono text-xs">
            {JSON.stringify(
              {
                organization_id: orgId,
                entra_tenant_id: tid,
                primary_domain: primaryDomain || null,
                allowed_email_domains: allowedDomains
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
                activate,
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
    let mapping: Record<string, string> | undefined;
    try {
      mapping = JSON.parse(roleMapping);
    } catch {
      toast.error("Role mapping must be valid JSON");
      throw new Error("invalid role mapping");
    }
    try {
      const result = await tenancyApi.linkEntraTenant({
        organization_id: orgId,
        entra_tenant_id: tid.trim(),
        primary_domain: primaryDomain || undefined,
        allowed_email_domains: allowedDomains
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        role_mapping: mapping,
        activate,
      });
      toast.success(`Linked org -> Entra tid (status: ${result.status})`);
      onCreated?.({ id: result.id, status: result.status });
    } catch (err) {
      toast.error("Link failed", {
        description: err instanceof Error ? err.message : String(err),
      });
      throw err;
    }
  };

  return (
    <Wizard
      title="Link Entra ID tenant"
      subtitle="AGENTS rule 44: org provisioning from Entra ID claims goes through EntraTenantLink."
      steps={steps}
      onFinish={onFinish}
    />
  );
}
