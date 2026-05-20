import { apiFetch } from "./client";

export interface DataHubStatus {
  configured: boolean;
  gms_url: string;
  env: string;
  platform: string;
  platform_instance: string;
  sync_enabled: boolean;
  sync_direction: string;
  external_platforms: string[];
  ping: { ok: boolean; config?: unknown; error?: string };
}

export interface DataHubLogEntry {
  id: string;
  direction: string;
  target: string;
  urn: string | null;
  platform: string | null;
  platform_instance: string | null;
  status: string;
  started_at: string;
  finished_at: string | null;
  error: string | null;
}

export const datahubApi = {
  status: () => apiFetch<DataHubStatus>("/datahub/status"),

  triggerSync: (direction?: "push" | "pull" | "bidirectional") =>
    apiFetch<Record<string, unknown>>("/datahub/sync", {
      method: "POST",
      ...(direction ? { query: { direction } } : {}),
    }),

  pushOne: (catalogId: string) =>
    apiFetch<{ emitted: boolean; urn?: string; error?: string }>("/datahub/push", {
      method: "POST",
      body: JSON.stringify({ catalog_id: catalogId }),
    }),

  pushAll: (limit = 1000) =>
    apiFetch<{ emitted: number; total: number; errors: string[] }>("/datahub/push-all", {
      method: "POST",
      query: { limit },
    }),

  pull: (platform?: string) =>
    apiFetch<Record<string, unknown>>("/datahub/pull", {
      method: "POST",
      ...(platform ? { query: { platform } } : {}),
    }),

  external: (limit = 200) =>
    apiFetch<{
      platforms: Array<{
        platform: string;
        platform_instance: string | null;
        urns: string[];
        last_pulled_at: string;
      }>;
    }>("/datahub/external", { query: { limit } }),

  log: (params?: { direction?: string; status?: string; limit?: number }) =>
    apiFetch<DataHubLogEntry[]>("/datahub/log", params ? { query: params } : {}),

  resolve: (input: {
    urn?: string;
    iceberg_identifier?: string;
    vt_symbol?: string;
  }) =>
    apiFetch<Record<string, unknown>>("/datahub/mappings/resolve", {
      method: "POST",
      body: JSON.stringify(input),
    }),
};
