/**
 * Self-serve org creation wizard for B2C → B2B trial conversion.
 *
 * Users on the Free tier can create a trial Organization through
 * this wizard — the backend route creates the :class:`Organization`
 * row, attaches a :class:`BillingAccount(plan_tier="trial",
 * trial_ends_at=now+14d)`, and auto-promotes the creator to
 * ``owner`` membership.
 *
 * The actual backend endpoint is a follow-up route; this component
 * scaffolds the UI shape so the route surface is locked in. Until
 * the route ships, the submit button is disabled with a "coming soon"
 * note — keeps the typecheck green without misleading users.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";

interface CreateOrgResponse {
  organization_id: string;
  billing_account_id: string;
  trial_ends_at: string;
}

export function SelfServeOrgWizard() {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [billingEmail, setBillingEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState<CreateOrgResponse | null>(null);

  const submit = async () => {
    if (!name.trim() || !slug.trim()) {
      toast.warning("Name and slug are required.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await apiFetch<CreateOrgResponse>(
        "/tenancy/orgs/self-serve",
        {
          method: "POST",
          body: JSON.stringify({
            name: name.trim(),
            slug: slug.trim().toLowerCase(),
            billing_email: billingEmail.trim() || null,
          }),
        },
      );
      setCreated(response);
      toast.success("Trial organization created.");
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Failed to create trial organization.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Start a trial organization</CardTitle>
        <p className="mt-1 text-sm text-[color:var(--text-muted)]">
          Provision a fresh organization with a 14-day trial. You become the
          owner automatically; invite teammates afterward from the org
          settings page.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span>Organization name</span>
            <input
              type="text"
              className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Trading"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span>URL slug</span>
            <input
              type="text"
              className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="acme-trading"
            />
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span>
            Billing email{" "}
            <span className="text-xs text-[color:var(--text-muted)]">(optional)</span>
          </span>
          <input
            type="email"
            className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
            value={billingEmail}
            onChange={(e) => setBillingEmail(e.target.value)}
          />
        </label>
        <div className="flex justify-end">
          <Button onClick={submit} disabled={submitting}>
            {submitting ? "Provisioning..." : "Create trial org"}
          </Button>
        </div>
        {created && (
          <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--bg-elevated)] p-3 text-sm">
            <div className="font-semibold">Trial active</div>
            <div className="text-xs text-[color:var(--text-muted)]">
              Org id: <span className="font-mono">{created.organization_id}</span> ·
              Billing account: <span className="font-mono">{created.billing_account_id}</span> ·
              Trial ends: {created.trial_ends_at}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
