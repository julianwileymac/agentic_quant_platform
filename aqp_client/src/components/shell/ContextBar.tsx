import { Building2, Beaker, FolderTree, Layers, Users2 } from "lucide-react";

import { EntityPicker } from "@/components/common/EntityPicker";
import { Badge } from "@/components/ui/badge";
import { useTenancyStore } from "@/store/tenancy";

/**
 * Phase 6 of the multi-tenant rollout. Renders a thin row of pickers
 * just below the TopBar so the user can pin the active org / team /
 * workspace / project / lab. The selection drives the
 * ``X-AQP-Org / -Team / -Workspace / -Project / -Lab`` request
 * headers emitted by ``getTenancyHeaders``, which in turn drives the
 * backend ``current_context`` dep + the MCP tool tenancy filters.
 *
 * The bar is collapsible / read-only on small screens to keep the
 * SandboxBanner amber strip prominent.
 */
export function ContextBar() {
  const orgId = useTenancyStore((s) => s.orgId);
  const teamId = useTenancyStore((s) => s.teamId);
  const workspaceId = useTenancyStore((s) => s.workspaceId);
  const projectId = useTenancyStore((s) => s.projectId);
  const labId = useTenancyStore((s) => s.labId);
  const setOrg = useTenancyStore((s) => s.setOrg);
  const setTeam = useTenancyStore((s) => s.setTeam);
  const setWorkspace = useTenancyStore((s) => s.setWorkspace);
  const setProject = useTenancyStore((s) => s.setProject);
  const setLab = useTenancyStore((s) => s.setLab);

  return (
    <div
      data-testid="context-bar"
      className="hidden items-center gap-3 border-b border-[var(--border)] bg-[var(--bg-sidebar)] px-4 py-1.5 text-xs md:flex"
    >
      <Badge variant="outline" className="gap-1">
        <Building2 className="size-3" /> Context
      </Badge>

      <ContextField icon={<Building2 className="size-3" />} label="ORG" value={orgId}>
        <EntityPicker
          kind="organizations"
          value={orgId}
          onChange={(id) => setOrg(id)}
          placeholder="Select org"
          clearable={false}
          className="min-w-[180px]"
        />
      </ContextField>

      <ContextField icon={<Users2 className="size-3" />} label="TEAM" value={teamId}>
        <EntityPicker
          kind="teams"
          value={teamId}
          onChange={(id) => setTeam(id)}
          placeholder="Select team"
          className="min-w-[160px]"
        />
      </ContextField>

      <ContextField icon={<FolderTree className="size-3" />} label="WS" value={workspaceId}>
        <EntityPicker
          kind="workspaces"
          value={workspaceId}
          onChange={(id) => setWorkspace(id)}
          placeholder="Select workspace"
          className="min-w-[200px]"
        />
      </ContextField>

      <ContextField icon={<Layers className="size-3" />} label="PROJ" value={projectId}>
        <EntityPicker
          kind="projects"
          value={projectId}
          onChange={(id) => setProject(id)}
          placeholder="Select project"
          className="min-w-[200px]"
        />
      </ContextField>

      <ContextField icon={<Beaker className="size-3" />} label="LAB" value={labId}>
        <EntityPicker
          kind="labs"
          value={labId}
          onChange={(id) => setLab(id)}
          placeholder="Select lab"
          className="min-w-[180px]"
        />
      </ContextField>
    </div>
  );
}

interface ContextFieldProps {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  children: React.ReactNode;
}

function ContextField({ icon, label, value, children }: ContextFieldProps) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="flex items-center gap-1 text-[10px] font-mono text-[var(--text-muted)]">
        {icon}
        {label}
      </span>
      <div className={value ? "" : "opacity-60"}>{children}</div>
    </div>
  );
}
