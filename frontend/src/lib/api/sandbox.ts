import { apiFetch } from "./client";

export interface SandboxSessionSummary {
  id: string;
  owner?: string | null;
  workspace_id?: string | null;
  project_id?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  components: string[];
  asset_keys: string[][];
  last_run_id?: string | null;
  log_summary: Array<Record<string, unknown>>;
  status: string;
}

export const SandboxApi = {
  list: async (): Promise<SandboxSessionSummary[]> =>
    apiFetch<SandboxSessionSummary[]>("/dagster/sandbox/sessions"),

  create: async (ttl_minutes = 60): Promise<SandboxSessionSummary> =>
    apiFetch<SandboxSessionSummary>("/dagster/sandbox/sessions", {
      method: "POST",
      body: JSON.stringify({ ttl_minutes }),
    }),

  get: async (id: string): Promise<SandboxSessionSummary> =>
    apiFetch<SandboxSessionSummary>(`/dagster/sandbox/sessions/${encodeURIComponent(id)}`),

  writeComponent: async (
    id: string,
    name: string,
    body: string,
  ): Promise<SandboxSessionSummary> =>
    apiFetch<SandboxSessionSummary>(
      `/dagster/sandbox/sessions/${encodeURIComponent(id)}/components`,
      {
        method: "POST",
        body: JSON.stringify({ name, body }),
      },
    ),

  loadAirbyte: async (
    id: string,
    airbyteConnectionId: string,
  ): Promise<SandboxSessionSummary> =>
    apiFetch<SandboxSessionSummary>(
      `/dagster/sandbox/sessions/${encodeURIComponent(id)}/airbyte`,
      {
        method: "POST",
        body: JSON.stringify({ airbyte_connection_id: airbyteConnectionId }),
      },
    ),

  load: async (id: string): Promise<SandboxSessionSummary> =>
    apiFetch<SandboxSessionSummary>(
      `/dagster/sandbox/sessions/${encodeURIComponent(id)}/load`,
      { method: "POST" },
    ),

  execute: async (id: string): Promise<{ task_id: string; stream_url: string }> =>
    apiFetch<{ task_id: string; stream_url: string }>(
      `/dagster/sandbox/sessions/${encodeURIComponent(id)}/execute`,
      { method: "POST" },
    ),

  teardown: async (id: string): Promise<unknown> =>
    apiFetch<unknown>(`/dagster/sandbox/sessions/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  janitor: async (): Promise<{ dropped: string[]; count: number }> =>
    apiFetch("/dagster/sandbox/janitor", { method: "POST" }),
};
