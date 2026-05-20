import { apiFetch } from "./client";

export type DiscoveryLifecycleState =
  | "ingested"
  | "pending"
  | "orphan"
  | "external_only";

export interface DiscoveryEntry {
  id: string;
  name: string;
  provider: string;
  domain?: string | null;
  lifecycle_state: DiscoveryLifecycleState;
  dataset_kind?: string | null;
  is_ingested: boolean;
  iceberg_identifier?: string | null;
  namespace?: string | null;
  medallion_layer?: string | null;
  description?: string | null;
  docs_url?: string | null;
  source_uri?: string | null;
  tags: string[];
  spec_hash?: string | null;
  external_spec: Record<string, unknown>;
  business_metadata: Record<string, unknown>;
  data_contract: Record<string, unknown>;
  suggested_connector?: string | null;
  suggested_kind?: string | null;
  airbyte_connection_id?: string | null;
  promote_url?: string | null;
  updated_at?: string | null;
}

export interface DiscoveryPage {
  items: DiscoveryEntry[];
  total: number;
  next_cursor: number | null;
  by_lifecycle: Record<string, number>;
}

export interface CreateExternalEntryPayload {
  name: string;
  provider?: string;
  domain?: string;
  description?: string | null;
  source_uri?: string | null;
  docs_url?: string | null;
  suggested_connector?: string | null;
  suggested_kind?: string | null;
  tags?: string[];
}

export interface UpdateEntryPayload {
  description?: string | null;
  docs_url?: string | null;
  source_uri?: string | null;
  suggested_connector?: string | null;
  suggested_kind?: string | null;
  tags?: string[] | null;
  business_metadata?: Record<string, unknown> | null;
  data_contract?: Record<string, unknown> | null;
}

export interface PromoteResponse {
  entry_id: string;
  target_kind: string;
  redirect_url: string;
  builder_state: Record<string, unknown>;
}

export const DiscoveryApi = {
  list: async (
    args: {
      lifecycle?: DiscoveryLifecycleState;
      provider?: string;
      kind?: string;
      search?: string;
      cursor?: number;
      limit?: number;
    } = {},
  ): Promise<DiscoveryPage> => {
    const query: Record<string, string | number> = {
      cursor: args.cursor ?? 0,
      limit: args.limit ?? 100,
    };
    if (args.lifecycle) query.lifecycle = args.lifecycle;
    if (args.provider) query.provider = args.provider;
    if (args.kind) query.kind = args.kind;
    if (args.search) query.search = args.search;
    return apiFetch<DiscoveryPage>("/discovery/entries", { query });
  },

  describe: async (id: string): Promise<DiscoveryEntry> =>
    apiFetch<DiscoveryEntry>(`/discovery/entries/${encodeURIComponent(id)}`),

  create: async (payload: CreateExternalEntryPayload): Promise<DiscoveryEntry> =>
    apiFetch<DiscoveryEntry>("/discovery/entries", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  patch: async (id: string, payload: UpdateEntryPayload): Promise<DiscoveryEntry> =>
    apiFetch<DiscoveryEntry>(`/discovery/entries/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  remove: async (id: string): Promise<unknown> =>
    apiFetch<unknown>(`/discovery/entries/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  promote: async (
    id: string,
    payload: { target_kind?: "airbyte_builder" | "fetcher_stub"; notes?: string } = {},
  ): Promise<PromoteResponse> =>
    apiFetch<PromoteResponse>(`/discovery/entries/${encodeURIComponent(id)}/promote`, {
      method: "POST",
      body: JSON.stringify({
        target_kind: payload.target_kind ?? "airbyte_builder",
        notes: payload.notes ?? null,
      }),
    }),
};
