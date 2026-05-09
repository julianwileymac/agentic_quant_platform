import { useState } from "react";

import { AdminCrudPage, CrudSheetFooter } from "@/components/admin/AdminCrudPage";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet } from "@/components/ui/sheet";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { createLab, deleteLab, type Lab, type Workspace } from "@/lib/api/tenancy";
import { formatTime } from "@/lib/utils";

export function LabsAdminRoute() {
  const list = useApiQuery<Lab[]>({
    queryKey: ["labs"],
    path: "/labs",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  return (
    <AdminCrudPage<Lab>
      title="Labs"
      subtitle="Workspace-scoped labs. RAG corpora and episodic memory are lab-scoped."
      rows={list.data ?? []}
      loading={list.isPending}
      onRefresh={() => list.refetch()}
      rowKey={(l) => l.id}
      columns={[
        { key: "slug", header: "Slug", width: 180, render: (l) => <span className="font-mono">{l.slug}</span> },
        { key: "name", header: "Name", render: (l) => <span className="font-medium">{l.name}</span> },
        {
          key: "workspace",
          header: "Workspace",
          width: 200,
          render: (l) => (
            <span className="font-mono text-[10px] text-[var(--text-secondary)]">{l.workspace_id}</span>
          ),
        },
        {
          key: "kernel_image",
          header: "Kernel",
          width: 200,
          render: (l) => <span className="font-mono text-xs">{l.kernel_image ?? "—"}</span>,
        },
        {
          key: "last_active_at",
          header: "Last active",
          width: 140,
          align: "right",
          render: (l) => (
            <span className="text-[var(--text-secondary)]">
              {l.last_active_at ? formatTime(l.last_active_at) : "—"}
            </span>
          ),
        },
        {
          key: "archived",
          header: "Archived",
          width: 100,
          render: (l) => <Badge variant={l.archived ? "warn" : "positive"}>{l.archived ? "yes" : "no"}</Badge>,
        },
      ]}
      confirmDeletePhrase={(l) => l.slug}
      deleteTitle={(l) => `Delete lab ${l.slug}`}
      deleteConsequence="Deleting a lab cascades to its corpora and episodic memory. Type the lab slug to confirm."
      onDelete={(l) => deleteLab(l.id)}
      createSheet={({ open, setOpen, onSaved }) => (
        <CreateLabSheet open={open} onClose={() => setOpen(false)} onSaved={onSaved} />
      )}
    />
  );
}

function CreateLabSheet({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const workspaces = useApiQuery<Workspace[]>({
    queryKey: ["workspaces", "for-lab-create"],
    path: "/workspaces",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [kernelImage, setKernelImage] = useState("python:3.11");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!slug.trim() || !name.trim() || !workspaceId) return;
    setSaving(true);
    try {
      await createLab({
        slug: slug.trim(),
        name: name.trim(),
        workspace_id: workspaceId,
        kernel_image: kernelImage.trim() || null,
        description: description.trim() || null,
      });
      toast.success(`Lab ${slug} created`);
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
      title="New lab"
      footer={
        <CrudSheetFooter
          onCancel={onClose}
          onSubmit={submit}
          saveLabel="Create lab"
          saving={saving}
          saveDisabled={!slug.trim() || !name.trim() || !workspaceId}
        />
      }
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor="lab-ws">Workspace</Label>
        <select
          id="lab-ws"
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
        <Label htmlFor="lab-slug">Slug</Label>
        <Input id="lab-slug" value={slug} onChange={(e) => setSlug(e.target.value)} className="font-mono" />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="lab-name">Name</Label>
        <Input id="lab-name" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="lab-kernel">Kernel image</Label>
        <Input id="lab-kernel" className="font-mono" value={kernelImage} onChange={(e) => setKernelImage(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="lab-desc">Description (optional)</Label>
        <Input id="lab-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
    </Sheet>
  );
}
