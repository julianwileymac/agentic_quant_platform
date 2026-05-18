import { apiFetch } from "./client";

export interface SinkKind {
  kind: string;
  display_name: string;
  description?: string;
  config_fields?: Array<{
    name: string;
    label?: string;
    type: string;
    required?: boolean;
    default?: unknown;
    options?: string[];
  }>;
  default_node_template?: { name: string; kwargs?: Record<string, unknown> };
  supported_domains?: string[];
  documentation_url?: string | null;
  tags?: string[];
}

export interface SinkSummary {
  id: string;
  name: string;
  kind: string;
  display_name: string;
  description?: string | null;
  config: Record<string, unknown>;
  tags?: string[];
  documentation_url?: string | null;
  requires_manifest_node?: boolean;
  current_version?: number;
  enabled?: boolean;
  annotations?: string[];
  meta?: Record<string, unknown>;
  workspace_id?: string | null;
  project_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CreateSinkRequest {
  name: string;
  kind: string;
  display_name?: string;
  description?: string;
  config?: Record<string, unknown>;
  tags?: string[];
  enabled?: boolean;
  notes?: string;
}

function path(id: string, suffix = ""): string {
  return `/sinks/${encodeURIComponent(id)}${suffix}`;
}

export const sinksApi = {
  listKinds: (): Promise<SinkKind[]> => apiFetch<SinkKind[]>("/sinks/kinds"),
  list: (params?: { kind?: string; enabled_only?: boolean; limit?: number }): Promise<SinkSummary[]> =>
    apiFetch<SinkSummary[]>("/sinks/", params ? { query: params } : {}),
  get: (id: string): Promise<SinkSummary> => apiFetch<SinkSummary>(path(id)),
  create: (body: CreateSinkRequest): Promise<SinkSummary> =>
    apiFetch<SinkSummary>("/sinks/", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<CreateSinkRequest>): Promise<SinkSummary> =>
    apiFetch<SinkSummary>(path(id), { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string): Promise<void> => apiFetch<void>(path(id), { method: "DELETE" }),
  materialise: (id: string, overrides: Record<string, unknown> = {}): Promise<{
    name: string;
    kwargs: Record<string, unknown>;
    enabled: boolean;
  }> =>
    apiFetch(path(id, "/materialise"), {
      method: "POST",
      body: JSON.stringify({ overrides }),
    }),
};
