import { useState } from "react";

import { AdminCrudPage, CrudSheetFooter } from "@/components/admin/AdminCrudPage";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet } from "@/components/ui/sheet";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { createTeam, deleteTeam, type Organization, type Team } from "@/lib/api/tenancy";
import { formatTime } from "@/lib/utils";

export function TeamsAdminRoute() {
  const list = useApiQuery<Team[]>({
    queryKey: ["teams"],
    path: "/teams",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  return (
    <AdminCrudPage<Team>
      title="Teams"
      subtitle="Org-scoped teams. Used for permissioning at the team-level scope on layered configs."
      rows={list.data ?? []}
      loading={list.isPending}
      onRefresh={() => list.refetch()}
      rowKey={(t) => t.id}
      columns={[
        { key: "slug", header: "Slug", width: 160, render: (t) => <span className="font-mono">{t.slug}</span> },
        { key: "name", header: "Name", render: (t) => <span className="font-medium">{t.name}</span> },
        {
          key: "org_id",
          header: "Org",
          width: 200,
          render: (t) => (
            <span className="font-mono text-[10px] text-[var(--text-secondary)]">{t.org_id}</span>
          ),
        },
        {
          key: "description",
          header: "Description",
          render: (t) => <span className="text-xs">{t.description ?? "—"}</span>,
        },
        {
          key: "created_at",
          header: "Created",
          width: 130,
          align: "right",
          render: (t) => (
            <span className="text-[var(--text-secondary)]">
              {t.created_at ? formatTime(t.created_at) : "—"}
            </span>
          ),
        },
      ]}
      confirmDeletePhrase={(t) => t.slug}
      deleteTitle={(t) => `Delete team ${t.slug}`}
      deleteConsequence="Deleting a team cascades to its memberships. Type the team slug to confirm."
      onDelete={(t) => deleteTeam(t.id)}
      createSheet={({ open, setOpen, onSaved }) => (
        <CreateTeamSheet open={open} onClose={() => setOpen(false)} onSaved={onSaved} />
      )}
    />
  );
}

interface CreateTeamSheetProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

function CreateTeamSheet({ open, onClose, onSaved }: CreateTeamSheetProps) {
  const orgs = useApiQuery<Organization[]>({
    queryKey: ["orgs", "for-team-create"],
    path: "/orgs",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [orgId, setOrgId] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!slug.trim() || !name.trim() || !orgId) return;
    setSaving(true);
    try {
      await createTeam({
        slug: slug.trim(),
        name: name.trim(),
        org_id: orgId,
        description: description.trim() || null,
      });
      toast.success(`Team ${slug} created`);
      setSlug("");
      setName("");
      setDescription("");
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
      title="New team"
      footer={
        <CrudSheetFooter
          onCancel={onClose}
          onSubmit={submit}
          saveLabel="Create team"
          saving={saving}
          saveDisabled={!slug.trim() || !name.trim() || !orgId}
        />
      }
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor="team-org">Organization</Label>
        <select
          id="team-org"
          value={orgId}
          onChange={(e) => setOrgId(e.target.value)}
          className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm text-[var(--text-primary)]"
        >
          <option value="">Select an org…</option>
          {(orgs.data ?? []).map((o) => (
            <option key={o.id} value={o.id}>
              {o.name} ({o.slug})
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="team-slug">Slug</Label>
        <Input id="team-slug" value={slug} onChange={(e) => setSlug(e.target.value)} className="font-mono" />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="team-name">Name</Label>
        <Input id="team-name" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="team-desc">Description (optional)</Label>
        <Input id="team-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
    </Sheet>
  );
}
