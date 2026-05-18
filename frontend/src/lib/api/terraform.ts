import { apiFetch } from "./client";

/**
 * Typed client for the `/terraform/*` REST surface. Mirrors the
 * `aqp.data.mcp.tools.terraform` MCP tools so any code path picks
 * whichever transport is cheaper (REST for SPA UI, MCP for agents).
 */

export type TerraformModuleKind =
  | "storage"
  | "pipeline"
  | "faas"
  | "agents"
  | "database"
  | "kubernetes"
  | "registry"
  | "networking"
  | "secrets"
  | "terraform_runner"
  | "composite";

export type TerraformProviderKind =
  | "local"
  | "docker"
  | "baremetal"
  | "rpi_cluster"
  | "aws"
  | "gcp"
  | "azure"
  | "hcp";

export type TerraformStateBackend = "local" | "s3" | "azurerm" | "gcs" | "hcp";

export type TerraformEnvironment = "local" | "paper" | "live" | "sandbox";

export type TerraformRunKind =
  | "plan"
  | "apply"
  | "destroy"
  | "refresh"
  | "import"
  | "state_pull"
  | "validate"
  | "unlock";

export type TerraformRunStatus =
  | "queued"
  | "running"
  | "errored"
  | "completed"
  | "cancelled"
  | "awaiting_approval"
  | "policy_failed";

export interface TerraformProvider {
  id: string;
  slug: string;
  name: string;
  kind: TerraformProviderKind;
  default_region?: string | null;
  status?: string;
  credential_key?: string | null;
}

export interface TerraformStackSummary {
  id: string;
  slug: string;
  name: string;
  module_kind: TerraformModuleKind;
  description?: string | null;
  current_version: number;
}

export interface TerraformWorkspace {
  id: string;
  slug: string;
  name: string;
  stack_spec_id?: string | null;
  provider_id?: string | null;
  environment: TerraformEnvironment;
  state_backend: TerraformStateBackend;
  state_uri?: string | null;
  hcp_workspace_id?: string | null;
  tenant_org_id?: string | null;
  archived: boolean;
}

export interface TerraformRun {
  id: string;
  terraform_workspace_id: string;
  spec_version_id?: string | null;
  run_kind: TerraformRunKind;
  status: TerraformRunStatus;
  started_by_user_id?: string | null;
  approved_by_user_id?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  exit_code?: number | null;
  halted: boolean;
  celery_task_id?: string | null;
  experiment_id?: string | null;
  plan_summary_json?: Record<string, unknown> | null;
  policy_check_result?: Record<string, unknown> | null;
  plan_artifact_uri?: string | null;
  apply_artifact_uri?: string | null;
  error?: string | null;
}

export interface DescribeWorkspaceResponse {
  workspace: TerraformWorkspace;
  last_run: TerraformRun | null;
  latest_state_version: {
    id: string;
    serial: number;
    lineage?: string | null;
    state_json_uri: string;
    outputs_redacted: Record<string, unknown>;
    resource_count?: number | null;
    created_at?: string | null;
  } | null;
}

export interface CreateStackPayload {
  name: string;
  slug: string;
  module_kind: TerraformModuleKind;
  cloud_provider: TerraformProviderKind;
  environment: TerraformEnvironment;
  description?: string;
  variables?: Record<string, unknown>;
  backend?: { kind: TerraformStateBackend; config?: Record<string, unknown> };
  provider?: {
    id?: string;
    kind: TerraformProviderKind;
    region?: string;
    config?: Record<string, unknown>;
  };
  module_source?: string;
  tags?: Record<string, string>;
  annotations?: Record<string, string>;
}

export interface CreateWorkspacePayload {
  slug: string;
  name: string;
  stack_spec_id: string;
  provider_id?: string;
  environment: TerraformEnvironment;
  state_backend?: TerraformStateBackend;
  state_uri?: string;
  hcp_workspace_id?: string;
  tenant_org_id?: string;
}

export const terraformApi = {
  // Providers
  listProviders: async (kind?: string): Promise<{ items: TerraformProvider[]; total: number }> =>
    apiFetch("/terraform/providers", { query: kind ? { kind } : {} }),
  createProvider: async (payload: {
    slug: string;
    name: string;
    kind: TerraformProviderKind;
    default_region?: string;
    config_json?: Record<string, unknown>;
    credential_key?: string;
  }): Promise<{ id: string; slug: string }> =>
    apiFetch("/terraform/providers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Stacks + versions
  listStacks: async (
    module_kind?: TerraformModuleKind,
  ): Promise<{ items: TerraformStackSummary[]; total: number }> =>
    apiFetch("/terraform/stacks", { query: module_kind ? { module_kind } : {} }),
  createStack: async (
    payload: CreateStackPayload,
  ): Promise<{ spec_version_id: string; spec_hash: string; slug: string }> =>
    apiFetch("/terraform/stacks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listStackVersions: async (
    spec_id: string,
  ): Promise<{ items: Array<{ id: string; version: number; spec_hash: string; notes?: string; created_at?: string }> }> =>
    apiFetch(`/terraform/stacks/${encodeURIComponent(spec_id)}/versions`),
  getStackVersion: async (
    spec_id: string,
    version_id: string,
  ): Promise<{
    id: string;
    version: number;
    spec_hash: string;
    payload_json: Record<string, unknown>;
    payload_hcl?: string | null;
  }> =>
    apiFetch(
      `/terraform/stacks/${encodeURIComponent(spec_id)}/versions/${encodeURIComponent(version_id)}`,
    ),

  // Workspaces
  listWorkspaces: async (args: {
    environment?: TerraformEnvironment;
    archived?: boolean;
  } = {}): Promise<{ items: TerraformWorkspace[]; total: number }> =>
    apiFetch("/terraform/workspaces", {
      query: {
        environment: args.environment ?? "",
        archived: args.archived ? "true" : "false",
      },
    }),
  getWorkspace: async (workspace_id: string): Promise<DescribeWorkspaceResponse> =>
    apiFetch(`/terraform/workspaces/${encodeURIComponent(workspace_id)}`),
  createWorkspace: async (
    payload: CreateWorkspacePayload,
  ): Promise<{ id: string; slug: string }> =>
    apiFetch("/terraform/workspaces", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  archiveWorkspace: async (workspace_id: string): Promise<{ id: string; archived: boolean }> =>
    apiFetch(`/terraform/workspaces/${encodeURIComponent(workspace_id)}`, {
      method: "DELETE",
    }),

  // Lifecycle
  plan: async (workspace_id: string): Promise<{ run_id: string }> =>
    apiFetch(`/terraform/workspaces/${encodeURIComponent(workspace_id)}/plan`, {
      method: "POST",
    }),
  apply: async (
    workspace_id: string,
    plan_run_id: string,
    approver_note?: string,
  ): Promise<{ run_id: string }> =>
    apiFetch(`/terraform/workspaces/${encodeURIComponent(workspace_id)}/apply`, {
      method: "POST",
      query: {
        plan_run_id,
        approver_note: approver_note ?? "",
      },
    }),
  destroy: async (
    workspace_id: string,
    confirmation_phrase: string,
  ): Promise<{ run_id: string }> =>
    apiFetch(`/terraform/workspaces/${encodeURIComponent(workspace_id)}/destroy`, {
      method: "POST",
      query: { confirmation_phrase },
    }),

  // Runs
  listRuns: async (args: {
    workspace_id?: string;
    status?: TerraformRunStatus;
    limit?: number;
  } = {}): Promise<{ items: TerraformRun[]; total: number }> =>
    apiFetch("/terraform/runs", {
      query: {
        workspace_id: args.workspace_id ?? "",
        status: args.status ?? "",
        limit: args.limit ?? 50,
      },
    }),
  getRun: async (run_id: string): Promise<TerraformRun> =>
    apiFetch(`/terraform/runs/${encodeURIComponent(run_id)}`),
  cancelRun: async (run_id: string): Promise<{ run_id: string; status: string }> =>
    apiFetch(`/terraform/runs/${encodeURIComponent(run_id)}/cancel`, {
      method: "POST",
    }),

  halt: async (): Promise<{ halted: number; run_ids: string[] }> =>
    apiFetch("/terraform/halt", { method: "POST" }),
};
