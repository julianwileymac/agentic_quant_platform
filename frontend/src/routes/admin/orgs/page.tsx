import { useState } from "react";

import { AdminCrudPage, CrudSheetFooter } from "@/components/admin/AdminCrudPage";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet } from "@/components/ui/sheet";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { createOrg, deleteOrg, type Organization } from "@/lib/api/tenancy";
import { formatTime } from "@/lib/utils";

export function OrgsAdminRoute() {
  const list = useApiQuery<Organization[]>({
    queryKey: ["orgs"],
    path: "/orgs",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  return (
    <AdminCrudPage<Organization>
      title="Organizations"
      subtitle="Top-level tenancy entities. Each org owns workspaces, teams, projects, labs."
      rows={list.data ?? []}
      loading={list.isPending}
      onRefresh={() => list.refetch()}
      rowKey={(o) => o.id}
      columns={[
        { key: "slug", header: "Slug", width: 160, render: (o) => <span className="font-mono">{o.slug}</span> },
        { key: "name", header: "Name", render: (o) => <span className="font-medium">{o.name}</span> },
        {
          key: "status",
          header: "Status",
          width: 110,
          render: (o) => (
            <Badge variant={o.status === "active" ? "positive" : "secondary"}>{o.status}</Badge>
          ),
        },
        {
          key: "billing_email",
          header: "Billing email",
          width: 240,
          render: (o) => (
            <span className="font-mono text-xs text-[var(--text-secondary)]">
              {o.billing_email ?? "—"}
            </span>
          ),
        },
        {
          key: "created_at",
          header: "Created",
          width: 130,
          align: "right",
          render: (o) => (
            <span className="text-[var(--text-secondary)]">
              {o.created_at ? formatTime(o.created_at) : "—"}
            </span>
          ),
        },
      ]}
      confirmDeletePhrase={(o) => o.slug}
      deleteTitle={(o) => `Delete org ${o.slug}`}
      deleteConsequence="Deleting an organization cascades to its workspaces, projects, and labs. This is irreversible. Type the org slug to confirm."
      onDelete={(o) => deleteOrg(o.id)}
      createSheet={({ open, setOpen, onSaved }) => (
        <CreateOrgSheet open={open} onClose={() => setOpen(false)} onSaved={onSaved} />
      )}
    />
  );
}

interface CreateOrgSheetProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

function CreateOrgSheet({ open, onClose, onSaved }: CreateOrgSheetProps) {
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [billingEmail, setBillingEmail] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!slug.trim() || !name.trim()) return;
    setSaving(true);
    try {
      await createOrg({
        slug: slug.trim(),
        name: name.trim(),
        billing_email: billingEmail.trim() || null,
      });
      toast.success(`Org ${slug} created`);
      setSlug("");
      setName("");
      setBillingEmail("");
      onSaved();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Create failed: ${msg}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="New organization"
      description="Slug must be unique and lowercase / hyphens only."
      footer={
        <CrudSheetFooter
          onCancel={onClose}
          onSubmit={submit}
          saveLabel="Create org"
          saving={saving}
          saveDisabled={!slug.trim() || !name.trim()}
        />
      }
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor="org-slug">Slug</Label>
        <Input id="org-slug" value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="acme-research" className="font-mono" />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="org-name">Name</Label>
        <Input id="org-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Research" />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="org-email">Billing email (optional)</Label>
        <Input id="org-email" type="email" value={billingEmail} onChange={(e) => setBillingEmail(e.target.value)} />
      </div>
    </Sheet>
  );
}
