import { apiFetch } from "./client";

/**
 * Typed client for the tenancy + onboarding REST surface.
 *
 * Two API shapes coexist:
 *
 * - **Direct functions** (`createOrg`, `listOrgs`, ...): used by the
 *   legacy admin CRUD pages (`routes/admin/{orgs,teams,users,...}/page.tsx`)
 *   and the explorer page. Each function maps 1:1 to a REST verb on
 *   `/orgs`, `/teams`, `/users`, etc.
 * - **`tenancyApi` object**: used by the Phase 7 onboarding wizards
 *   (`OrgCreateWizard`, `EntraTenantLinkWizard`, `UserInviteWizard`).
 *   Wraps the richer `/tenancy/*` surface introduced in
 *   `aqp/api/routes/tenancy.py` with grouped methods.
 */

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export interface Organization {
  id: string;
  slug: string;
  name: string;
  billing_email?: string | null;
  status: string;
  meta?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Team {
  id: string;
  org_id: string;
  slug: string;
  name: string;
  description?: string | null;
  meta?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  auth_subject?: string | null;
  auth_provider: string;
  status: string;
  avatar_url?: string | null;
  meta?: Record<string, unknown>;
  last_login_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Workspace {
  id: string;
  org_id: string;
  slug: string;
  name: string;
  description?: string | null;
  visibility: string;
  archived: boolean;
  settings?: Record<string, unknown>;
  meta?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Project {
  id: string;
  workspace_id: string;
  slug: string;
  name: string;
  description?: string | null;
  archived: boolean;
  settings?: Record<string, unknown>;
  meta?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Lab {
  id: string;
  workspace_id: string;
  slug: string;
  name: string;
  description?: string | null;
  kernel_image?: string | null;
  archived: boolean;
  last_active_at?: string | null;
  settings?: Record<string, unknown>;
  meta?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Membership {
  id: string;
  user_id: string;
  uid?: string | null;
  email?: string | null;
  scope_kind: string;
  scope_id: string;
  role: string;
  live_control: boolean;
  permission?: string | null;
  granted_at?: string | null;
  expires_at?: string | null;
  [key: string]: unknown;
}

export interface WhoAmI {
  user: User | null;
  memberships: Membership[];
  is_default: boolean;
  display_name?: string | null;
  email?: string | null;
  auth_provider?: string | null;
  picture?: string | null;
  [key: string]: unknown;
}

// Explorer-page-only projection types (consumed from the explorer
// route's preconfigured /explorer/* endpoints).
export interface ProjectStrategy {
  id: string;
  name: string;
  version: number;
  status: string;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface ProjectBacktest {
  id: string;
  strategy_id: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  metrics?: Record<string, unknown>;
  sharpe?: number | null;
  total_return?: number | null;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface ProjectAgent {
  id: string;
  name: string;
  kind?: string | null;
  status?: string | null;
  role?: string | null;
  current_version?: number | null;
  [key: string]: unknown;
}

export interface ProjectAgentRun {
  id: string;
  agent_id: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  spec_name?: string | null;
  cost_usd?: number | null;
  [key: string]: unknown;
}

export interface LabCorpus {
  id: string;
  name: string;
  domain?: string | null;
  chunk_count?: number | null;
  chunks_count?: number | null;
  order?: number | null;
  l1?: string | null;
  l2?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface LabMemoryEntry {
  id: string;
  kind: string;
  summary: string;
  created_at?: string | null;
  role?: string | null;
  vt_symbol?: string | null;
  situation?: string | null;
  lesson?: string | null;
  [key: string]: unknown;
}

export interface EntraTenantLinkRow {
  id: string;
  organization_id: string | null;
  entra_tenant_id: string;
  primary_domain?: string | null;
  display_name?: string | null;
  status: "pending" | "active" | "revoked" | "suspended";
  allowed_email_domains?: string | null;
  role_mapping?: Record<string, string> | null;
  approved_at?: string | null;
  created_at?: string | null;
}

// Backwards-compat alias for code that imports MembershipRow.
export type MembershipRow = Membership;
export type OrganizationRow = Organization;

// ---------------------------------------------------------------------------
// Legacy direct-function API (used by admin CRUD pages + explorer)
// ---------------------------------------------------------------------------

export const listOrgs = async (): Promise<Organization[]> =>
  apiFetch<Organization[]>("/orgs");

export const createOrg = async (
  body: Partial<Organization>,
): Promise<Organization> =>
  apiFetch<Organization>("/orgs", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const deleteOrg = async (id: string): Promise<void> => {
  await apiFetch<unknown>(`/orgs/${encodeURIComponent(id)}`, { method: "DELETE" });
};

export const listTeams = async (orgId?: string): Promise<Team[]> =>
  apiFetch<Team[]>("/teams", { query: orgId ? { org_id: orgId } : {} });

export const createTeam = async (
  body: Partial<Team>,
): Promise<Team> =>
  apiFetch<Team>("/teams", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const deleteTeam = async (id: string): Promise<void> => {
  await apiFetch<unknown>(`/teams/${encodeURIComponent(id)}`, { method: "DELETE" });
};

export const listUsers = async (): Promise<User[]> =>
  apiFetch<User[]>("/users");

export const createUser = async (
  body: Partial<User>,
): Promise<User> =>
  apiFetch<User>("/users", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const deleteUser = async (id: string): Promise<void> => {
  await apiFetch<unknown>(`/users/${encodeURIComponent(id)}`, { method: "DELETE" });
};

export const listWorkspaces = async (orgId?: string): Promise<Workspace[]> =>
  apiFetch<Workspace[]>("/workspaces", { query: orgId ? { org_id: orgId } : {} });

export const createWorkspace = async (
  body: Partial<Workspace>,
): Promise<Workspace> =>
  apiFetch<Workspace>("/workspaces", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const deleteWorkspace = async (id: string): Promise<void> => {
  await apiFetch<unknown>(`/workspaces/${encodeURIComponent(id)}`, { method: "DELETE" });
};

export const listWorkspaceLabs = async (workspaceId: string): Promise<Lab[]> =>
  apiFetch<Lab[]>(`/workspaces/${encodeURIComponent(workspaceId)}/labs`);

export const listWorkspaceProjects = async (
  workspaceId: string,
): Promise<Project[]> =>
  apiFetch<Project[]>(`/workspaces/${encodeURIComponent(workspaceId)}/projects`);

export const listWorkspaceCollaborators = async (
  workspaceId: string,
): Promise<Membership[]> =>
  apiFetch<Membership[]>(`/workspaces/${encodeURIComponent(workspaceId)}/members`);

export const listProjects = async (workspaceId?: string): Promise<Project[]> =>
  apiFetch<Project[]>("/projects", {
    query: workspaceId ? { workspace_id: workspaceId } : {},
  });

export const createProject = async (
  body: Partial<Project>,
): Promise<Project> =>
  apiFetch<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const deleteProject = async (id: string): Promise<void> => {
  await apiFetch<unknown>(`/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
};

export const listLabs = async (workspaceId?: string): Promise<Lab[]> =>
  apiFetch<Lab[]>("/labs", {
    query: workspaceId ? { workspace_id: workspaceId } : {},
  });

export const createLab = async (body: Partial<Lab>): Promise<Lab> =>
  apiFetch<Lab>("/labs", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const deleteLab = async (id: string): Promise<void> => {
  await apiFetch<unknown>(`/labs/${encodeURIComponent(id)}`, { method: "DELETE" });
};

// ---------------------------------------------------------------------------
// Layered configs (used by /admin/configs)
// ---------------------------------------------------------------------------

export const getEffectiveConfig = async (
  namespace: string,
): Promise<Record<string, unknown>> =>
  apiFetch<Record<string, unknown>>("/configs/effective", {
    query: { namespace },
  });

export const getConfigLayer = async (
  scope: string,
  scopeId: string,
  namespace: string,
): Promise<Record<string, unknown>> =>
  apiFetch<Record<string, unknown>>("/configs/layer", {
    query: { scope, scope_id: scopeId, namespace },
  });

export const setConfigLayer = async (
  scope: string,
  scopeId: string,
  namespace: string,
  payload: Record<string, unknown>,
  conflict?: string,
): Promise<{ overlay_id: string; [key: string]: unknown }> =>
  apiFetch<{ overlay_id: string; [key: string]: unknown }>("/configs/layer", {
    method: "POST",
    body: JSON.stringify({
      scope,
      scope_id: scopeId,
      namespace,
      payload,
      conflict_strategy: conflict,
    }),
  });

export const clearConfigLayer = async (
  scope: string,
  scopeId: string,
  namespace: string,
): Promise<void> => {
  await apiFetch<unknown>("/configs/layer", {
    method: "DELETE",
    body: JSON.stringify({ scope, scope_id: scopeId, namespace }),
  });
};

// ---------------------------------------------------------------------------
// Phase 7 — onboarding wizards (`tenancyApi` object)
// ---------------------------------------------------------------------------

export const tenancyApi = {
  listOrgs: async (args: {
    prefix?: string;
    status?: string;
    limit?: number;
  } = {}): Promise<{ items: Organization[]; total: number }> =>
    apiFetch("/tenancy/organizations", {
      query: {
        prefix: args.prefix ?? "",
        status: args.status ?? "",
        limit: args.limit ?? 50,
      },
    }),

  createOrg: async (payload: {
    name: string;
    slug: string;
    billing_email?: string | undefined;
    description?: string | undefined;
    seed_default_structure?: boolean | undefined;
  }): Promise<{
    organization: Organization;
    team_id: string | null;
    workspace_id: string | null;
    project_id: string | null;
    lab_id: string | null;
  }> =>
    apiFetch("/tenancy/organizations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listMemberships: async (args: {
    user_id?: string;
    scope_kind?: string;
    scope_id?: string;
    limit?: number;
  } = {}): Promise<{ items: Membership[]; total: number }> =>
    apiFetch("/tenancy/memberships", {
      query: {
        user_id: args.user_id ?? "",
        scope_kind: args.scope_kind ?? "",
        scope_id: args.scope_id ?? "",
        limit: args.limit ?? 100,
      },
    }),

  grantRole: async (payload: {
    user_id: string;
    scope_kind: string;
    scope_id: string;
    role: string;
    live_control?: boolean;
    expires_at_iso?: string;
  }): Promise<Membership & { created: boolean; upgraded: boolean }> =>
    apiFetch("/tenancy/memberships", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  invite: async (payload: {
    email: string;
    org_id: string;
    role?: string | undefined;
    scope_kind?: string | undefined;
    scope_id?: string | undefined;
    display_name?: string | undefined;
    send_entra_b2b_invitation?: boolean | undefined;
  }): Promise<{
    user_id: string;
    membership_id: string;
    created_user: boolean;
    entra_invitation: Record<string, unknown> | null;
  }> =>
    apiFetch("/tenancy/invites", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listEntraLinks: async (args: {
    organization_id?: string;
    status?: string;
  } = {}): Promise<{ items: EntraTenantLinkRow[]; total: number }> =>
    apiFetch("/tenancy/entra-links", {
      query: {
        organization_id: args.organization_id ?? "",
        status: args.status ?? "",
      },
    }),

  linkEntraTenant: async (payload: {
    organization_id: string;
    entra_tenant_id: string;
    primary_domain?: string | undefined;
    display_name?: string | undefined;
    allowed_email_domains?: string[] | undefined;
    role_mapping?: Record<string, string> | undefined;
    activate?: boolean | undefined;
  }): Promise<{
    id: string;
    organization_id: string;
    entra_tenant_id: string;
    primary_domain?: string | null;
    status: string;
    created: boolean;
  }> =>
    apiFetch("/tenancy/entra-links", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
