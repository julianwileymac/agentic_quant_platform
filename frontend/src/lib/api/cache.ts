import { apiFetch } from "./client";

/**
 * Cache categories backed by the FastAPI ``/cache/*`` endpoints. Kept in
 * sync with :data:`aqp.cache.keys.CACHE_CATEGORIES`. Adding a category
 * here without populating it on the backend is a no-op (the GET
 * returns an empty page).
 *
 * Phase 5 added tenancy + spec + polymorphic Resource categories so the
 * EntityPicker can drive the new ContextBar dropdowns and the strategy
 * template browser.
 */
export type CacheCategory =
  // Original (data fabric phase 0)
  | "datasets"
  | "namespaces"
  | "sink_kinds"
  | "sink_names"
  | "airbyte_connectors"
  | "projects"
  | "credentials"
  | "dataset_kinds"
  // Tenancy (Phase 5 multi-tenant rollout)
  | "organizations"
  | "teams"
  | "users"
  | "workspaces"
  | "labs"
  | "experiments"
  | "tests"
  // Specs (Phase 5)
  | "agents"
  | "bots"
  | "rl_experiments"
  | "analysis_specs"
  // Polymorphic content + LEAN templates (Phase 5 + Phase 7)
  | "strategy_templates"
  | "resources"
  // Phase 7 — Terraform IaC + Entra ID + cloud K8s explorer
  | "terraform_workspaces"
  | "terraform_providers"
  | "terraform_stacks"
  | "cloud_providers"
  | "entra_tenants"
  | "k8s_namespaces"
  | "k8s_clusters";

export interface CacheItem {
  id: string;
  name: string;
  [extra: string]: unknown;
}

export interface CachePage {
  category: string;
  items: CacheItem[];
  next_cursor?: number | null;
  total: number;
}

export interface CacheHealth {
  enabled: boolean;
  remote: boolean;
  members: Record<string, number>;
  stamps: Record<string, string | null>;
  info: Record<string, unknown>;
}

const CACHE_PATH: Record<CacheCategory, string> = {
  datasets: "/cache/datasets",
  namespaces: "/cache/namespaces",
  sink_kinds: "/cache/sink_kinds",
  sink_names: "/cache/sink_names",
  airbyte_connectors: "/cache/airbyte_connectors",
  projects: "/cache/projects",
  credentials: "/cache/credentials",
  dataset_kinds: "/cache/dataset_kinds",
  organizations: "/cache/organizations",
  teams: "/cache/teams",
  users: "/cache/users",
  workspaces: "/cache/workspaces",
  labs: "/cache/labs",
  experiments: "/cache/experiments",
  tests: "/cache/tests",
  agents: "/cache/agents",
  bots: "/cache/bots",
  rl_experiments: "/cache/rl_experiments",
  analysis_specs: "/cache/analysis_specs",
  strategy_templates: "/cache/strategy_templates",
  resources: "/cache/resources",
  // Phase 7 — Terraform IaC categories. The backend's MetadataPrefetcher
  // serves these out of /cache/<category>; missing populators degrade to
  // an empty page (the EntityPicker still renders).
  terraform_workspaces: "/cache/terraform_workspaces",
  terraform_providers: "/cache/terraform_providers",
  terraform_stacks: "/cache/terraform_stacks",
  cloud_providers: "/cache/cloud_providers",
  entra_tenants: "/cache/entra_tenants",
  k8s_namespaces: "/cache/k8s_namespaces",
  k8s_clusters: "/cache/k8s_clusters",
};

export const CacheApi = {
  page: async (
    category: CacheCategory,
    args: { prefix?: string; cursor?: number; limit?: number } = {},
  ): Promise<CachePage> =>
    apiFetch<CachePage>(CACHE_PATH[category], {
      query: {
        prefix: args.prefix ?? "",
        cursor: args.cursor ?? 0,
        limit: args.limit ?? 50,
      },
    }),

  describe: async (category: CacheCategory, identifier: string): Promise<CacheItem> =>
    apiFetch<CacheItem>(`${CACHE_PATH[category]}/${encodeURIComponent(identifier)}`),

  health: async (): Promise<CacheHealth> => apiFetch<CacheHealth>("/cache/health"),

  refresh: async (): Promise<unknown> => apiFetch<unknown>("/cache/refresh"),
};
