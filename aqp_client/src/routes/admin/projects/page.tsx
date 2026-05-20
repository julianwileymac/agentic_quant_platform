import { useState } from "react";

import { AdminCrudPage, CrudSheetFooter } from "@/components/admin/AdminCrudPage";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet } from "@/components/ui/sheet";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { createProject, deleteProject, type Project, type Workspace } from "@/lib/api/tenancy";
import { formatTime } from "@/lib/utils";

export function ProjectsAdminRoute() {
  const list = useApiQuery<Project[]>({
    queryKey: ["projects"],
    path: "/projects",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  return (
    <AdminCrudPage<Project>
      title="Projects"
      subtitle="Workspace-scoped projects. Strategies, backtests, and agents are project-scoped."
      rows={list.data ?? []}
      loading={list.isPending}
      onRefresh={() => list.refetch()}
      rowKey={(p) => p.id}
      columns={[
        { key: "slug", header: "Slug", width: 180, render: (p) => <span className="font-mono">{p.slug}</span> },
        { key: "name", header: "Name", render: (p) => <span className="font-medium">{p.name}</span> },
        {
          key: "workspace",
          header: "Workspace",
          width: 200,
          render: (p) => (
            <span className="font-mono text-[10px] text-[var(--text-secondary)]">{p.workspace_id}</span>
          ),
        },
        {
          key: "archived",
          header: "Archived",
          width: 110,
          render: (p) => <Badge variant={p.archived ? "warn" : "positive"}>{p.archived ? "yes" : "no"}</Badge>,
        },
        {
          key: "updated_at",
          header: "Updated",
          width: 140,
          align: "right",
          render: (p) => (
            <span className="text-[var(--text-secondary)]">
              {p.updated_at ? formatTime(p.updated_at) : "—"}
            </span>
          ),
        },
      ]}
      confirmDeletePhrase={(p) => p.slug}
      deleteTitle={(p) => `Delete project ${p.slug}`}
      deleteConsequence="Deleting a project cascades to its strategies, backtests, agents, and runs. Type the project slug to confirm."
      onDelete={(p) => deleteProject(p.id)}
      createSheet={({ open, setOpen, onSaved }) => (
        <CreateProjectSheet open={open} onClose={() => setOpen(false)} onSaved={onSaved} />
      )}
    />
  );
}

function CreateProjectSheet({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const workspaces = useApiQuery<Workspace[]>({
    queryKey: ["workspaces", "for-project-create"],
    path: "/workspaces",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!slug.trim() || !name.trim() || !workspaceId) return;
    setSaving(true);
    try {
      await createProject({
        slug: slug.trim(),
        name: name.trim(),
        workspace_id: workspaceId,
        description: description.trim() || null,
      });
      toast.success(`Project ${slug} created`);
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
      title="New project"
      footer={
        <CrudSheetFooter
          onCancel={onClose}
          onSubmit={submit}
          saveLabel="Create project"
          saving={saving}
          saveDisabled={!slug.trim() || !name.trim() || !workspaceId}
        />
      }
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor="proj-ws">Workspace</Label>
        <select
          id="proj-ws"
          value={workspaceId}
          onChange={(e) => setWorkspaceId(e.target.value)}
          className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm text-[var(--text-primary)]"
        >
          <option value="">Select a workspace…</option>
          {(workspaces.data ?? []).map((w) => (
            <option key={w.id} value={w.id}>
              {w.name} ({w.slug})
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="proj-slug">Slug</Label>
        <Input id="proj-slug" value={slug} onChange={(e) => setSlug(e.target.value)} className="font-mono" />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="proj-name">Name</Label>
        <Input id="proj-name" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="proj-desc">Description (optional)</Label>
        <Input id="proj-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
    </Sheet>
  );
}
