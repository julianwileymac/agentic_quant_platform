import { useState } from "react";

import { Wizard, type WizardStepDescriptor } from "@/components/common/Wizard";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { tenancyApi } from "@/lib/api/tenancy";

/**
 * Four-step org creation wizard.
 *
 *   1. Name & slug
 *   2. Billing email
 *   3. Default structure preview (driven by configs/tenants/tenant_default_template.yaml)
 *   4. Review & create
 */
interface Props {
  onCreated?: (organization: { id: string; slug: string; name: string }) => void;
}

export function OrgCreateWizard({ onCreated }: Props) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [billingEmail, setBillingEmail] = useState("");
  const [seedDefault, setSeedDefault] = useState(true);

  const steps: WizardStepDescriptor[] = [
    {
      id: "identity",
      title: "Name & slug",
      validate: () => name.trim().length >= 2 && /^[a-z0-9][a-z0-9-]*$/.test(slug),
      render: () => (
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Organization name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Slug (URL identifier)</Label>
            <Input
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase())}
              placeholder="wiley-tech"
            />
            <p className="text-xs text-[var(--text-secondary)]">
              Lowercase letters, numbers, and hyphens. Must start with a letter.
            </p>
          </div>
        </div>
      ),
    },
    {
      id: "billing",
      title: "Billing email",
      optional: true,
      render: () => (
        <div className="space-y-1">
          <Label>Billing email (optional)</Label>
          <Input
            type="email"
            value={billingEmail}
            onChange={(e) => setBillingEmail(e.target.value)}
            placeholder="billing@wiley.tech"
          />
        </div>
      ),
    },
    {
      id: "default-structure",
      title: "Default structure",
      render: () => (
        <div className="space-y-3 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={seedDefault}
              onChange={(e) => setSeedDefault(e.target.checked)}
            />
            Seed default team / workspace / project / lab (Core / Main)
          </label>
          <p className="text-xs text-[var(--text-secondary)]">
            Uses configs/tenants/tenant_default_template.yaml. Owner Memberships
            on every seeded scope are granted to you automatically.
          </p>
        </div>
      ),
    },
    {
      id: "review",
      title: "Review",
      render: () => (
        <pre className="overflow-x-auto whitespace-pre-wrap rounded-sm border border-[var(--border)] p-3 font-mono text-xs">
          {JSON.stringify(
            {
              name,
              slug,
              billing_email: billingEmail || null,
              seed_default_structure: seedDefault,
            },
            null,
            2,
          )}
        </pre>
      ),
    },
  ];

  const onFinish = async () => {
    try {
      const result = await tenancyApi.createOrg({
        name,
        slug,
        billing_email: billingEmail || undefined,
        seed_default_structure: seedDefault,
      });
      toast.success(`Created organization ${result.organization.slug}`);
      onCreated?.(result.organization);
    } catch (err) {
      toast.error("Create failed", {
        description: err instanceof Error ? err.message : String(err),
      });
      throw err;
    }
  };

  return (
    <Wizard
      title="Create organization"
      subtitle="Seed a new AQP tenant with the default team / workspace / project / lab structure."
      steps={steps}
      onFinish={onFinish}
    />
  );
}
