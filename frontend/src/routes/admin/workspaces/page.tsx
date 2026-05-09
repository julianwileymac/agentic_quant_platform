import { useState } from "react";

import { AdminCrudPage, CrudSheetFooter } from "@/components/admin/AdminCrudPage";
import { Numeric } from "@/components/common/Numeric";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet } from "@/components/ui/sheet";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaceCollaborators,
  listWorkspaceLabs,
  listWorkspaceProjects,
  type Organization,
  type Workspace,
} from "@/lib/api/tenancy";
import { formatTime } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";

const VISIBILITY = ["private", "org", "public"] as const;

export function WorkspacesAdminRoute() {
  const list = useApiQuery<Workspace[]>({
    queryKey: ["workspaces"],
    path: "/workspaces",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const [detail, setDetail] = useState<Workspace | null>(null);

  return (
    <>
      <AdminCrudPage<Workspace>
        title="Workspaces"
        subtitle="Org-scoped workspaces. Click a row to inspect projects / labs / collaborators."
        rows={list.data ?? []}
        loading={list.isPending}
        onRefresh={() => list.refetch()}
        rowKey={(w) => w.id}
        onRowClick={(w) => setDetail(w)}
        columns={[
          { key: "slug", header: "Slug", width: 180, render: (w) => <span className="font-mono">{w.slug}</span> },
          { key: "name", header: "Name", render: (w) => <span className="font-medium">{w.name}</span> },
          {
            key: "visibility",
            header: "Visibility",
            width: 110,
            render: (w) => <Badge variant="secondary">{w.visibility}</Badge>,
          },
          {
            key: "archived",
            header: "Archived",
            width: 100,
            render: (w) => <Badge variant={w.archived ? "warn" : "positive"}>{w.archived ? "yes" : "no"}</Badge>,
          },
          {
            key: "updated_at",
            header: "Updated",
            width: 140,
            align: "right",
            render: (w) => (
              <span className="text-[var(--text-secondary)]">
                {w.updated_at ? formatTime(w.updated_at) : "—"}
              </span>
            ),
          },
        ]}
        confirmDeletePhrase={(w) => w.slug}
        deleteTitle={(w) => `Delete workspace ${w.slug}`}
        deleteConsequence="Deleting a workspace cascades to its projects, labs, datasets, and saved charts. Type the workspace slug to confirm."
        onDelete={(w) => deleteWorkspace(w.id)}
        createSheet={({ open, setOpen, onSaved }) => (
          <CreateWorkspaceSheet open={open} onClose={() => setOpen(false)} onSaved={onSaved} />
        )}
      />
      {detail ? (
        <WorkspaceDetailSheet workspace={detail} onClose={() => setDetail(null)} />
      ) : null}
    </>
  );
}

function CreateWorkspaceSheet({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const orgs = useApiQuery<Organization[]>({
    queryKey: ["orgs", "for-ws-create"],
    path: "/orgs",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [orgId, setOrgId] = useState("");
  const [visibility, setVisibility] = useState<(typeof VISIBILITY)[number]>("private");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!slug.trim() || !name.trim() || !orgId) return;
    setSaving(true);
    try {
      await createWorkspace({
        slug: slug.trim(),
        name: name.trim(),
        org_id: orgId,
        visibility,
        description: description.trim() || null,
      });
      toast.success(`Workspace ${slug} created`);
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
      title="New workspace"
      footer={
        <CrudSheetFooter
          onCancel={onClose}
          onSubmit={submit}
          saveLabel="Create workspace"
          saving={saving}
          saveDisabled={!slug.trim() || !name.trim() || !orgId}
        />
      }
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor="ws-org">Organization</Label>
        <select
          id="ws-org"
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
        <Label htmlFor="ws-slug">Slug</Label>
        <Input id="ws-slug" value={slug} onChange={(e) => setSlug(e.target.value)} className="font-mono" />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="ws-name">Name</Label>
        <Input id="ws-name" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="ws-vis">Visibility</Label>
        <select
          id="ws-vis"
          value={visibility}
          onChange={(e) => setVisibility(e.target.value as (typeof VISIBILITY)[number])}
          className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm text-[var(--text-primary)]"
        >
          {VISIBILITY.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="ws-desc">Description (optional)</Label>
        <Input id="ws-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
    </Sheet>
  );
}

interface WorkspaceDetailSheetProps {
  workspace: Workspace;
  onClose: () => void;
}

function WorkspaceDetailSheet({ workspace, onClose }: WorkspaceDetailSheetProps) {
  const projects = useQuery({
    queryKey: ["workspaces", workspace.id, "projects"],
    queryFn: () => listWorkspaceProjects(workspace.id),
  });
  const labs = useQuery({
    queryKey: ["workspaces", workspace.id, "labs"],
    queryFn: () => listWorkspaceLabs(workspace.id),
  });
  const collaborators = useQuery({
    queryKey: ["workspaces", workspace.id, "collaborators"],
    queryFn: () => listWorkspaceCollaborators(workspace.id),
  });

  return (
    <Sheet
      open
      onOpenChange={(o) => !o && onClose()}
      title={workspace.name}
      description={`workspace.${workspace.slug}`}
      widthClass="max-w-xl"
    >
      <SubSection
        title="Projects"
        count={projects.data?.length}
        loading={projects.isPending}
        empty="No projects."
      >
        <ul className="divide-y divide-[var(--border-subtle)]">
          {(projects.data ?? []).map((p) => (
            <li key={p.id} className="flex items-center justify-between py-1.5 text-xs">
              <span className="font-mono">{p.slug}</span>
              <span className="text-[var(--text-secondary)]">{p.name}</span>
              <Badge variant={p.archived ? "warn" : "positive"} className="text-[9px]">
                {p.archived ? "archived" : "active"}
              </Badge>
            </li>
          ))}
        </ul>
      </SubSection>
      <SubSection
        title="Labs"
        count={labs.data?.length}
        loading={labs.isPending}
        empty="No labs."
      >
        <ul className="divide-y divide-[var(--border-subtle)]">
          {(labs.data ?? []).map((l) => (
            <li key={l.id} className="flex items-center justify-between py-1.5 text-xs">
              <span className="font-mono">{l.slug}</span>
              <span className="text-[var(--text-secondary)]">{l.kernel_image ?? "default kernel"}</span>
              <Badge variant={l.archived ? "warn" : "positive"} className="text-[9px]">
                {l.archived ? "archived" : "active"}
              </Badge>
            </li>
          ))}
        </ul>
      </SubSection>
      <SubSection
        title="Collaborators"
        count={collaborators.data?.length}
        loading={collaborators.isPending}
        empty="No collaborators."
      >
        <ul className="divide-y divide-[var(--border-subtle)]">
          {(collaborators.data ?? []).map((c) => (
            <li key={c.uid} className="flex items-center justify-between py-1.5 text-xs">
              <span className="font-mono">{c.email}</span>
              <Badge variant="secondary" className="text-[9px]">
                {c.permission}
              </Badge>
              {c.live_control ? <Badge variant="warn" className="text-[9px]">live</Badge> : null}
            </li>
          ))}
        </ul>
      </SubSection>
    </Sheet>
  );
}

interface SubSectionProps {
  title: string;
  count?: number | undefined;
  loading: boolean;
  empty: string;
  children: React.ReactNode;
}

function SubSection({ title, count, loading, empty, children }: SubSectionProps) {
  return (
    <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3">
      <div className="mb-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
        <span>{title}</span>
        <Numeric value={count ?? null} kind="integer" digits={0} color="neutral" />
      </div>
      {loading ? (
        <p className="text-xs text-[var(--text-secondary)]">Loading…</p>
      ) : count === 0 ? (
        <p className="text-xs italic text-[var(--text-secondary)]">{empty}</p>
      ) : (
        children
      )}
    </div>
  );
}
