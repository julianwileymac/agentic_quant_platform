import { apiFetch } from "./client";

export type AssistantMode = "agent" | "workflow";

export interface AssistantSpecSummary {
  name: string;
  description?: string;
  mode: AssistantMode;
  target_ref: string;
  snapshot_hash: string;
  annotations?: string[];
  template_target?: string;
}

export interface AssistantSpecDetail extends AssistantSpecSummary {
  payload: Record<string, unknown>;
}

export interface AssistantSessionSummary {
  id: string;
  assistant_spec_name: string;
  title: string | null;
  created_at?: string | null;
  last_active_at?: string | null;
  closed_at?: string | null;
}

export interface AssistantTaskResponse {
  task_id: string;
  status: string;
  stream_url: string;
}

export interface AssistantRunSummary {
  id: string;
  assistant_spec_name: string;
  status: string;
  target_kind: string;
  target_ref: string;
  target_run_kind?: string | null;
  target_run_id?: string | null;
  task_id?: string | null;
  session_id?: string | null;
  cost_usd?: number;
  halted?: boolean;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

export interface AssistantRunEventEntry {
  seq: number;
  kind: string;
  name: string;
  attributes: Record<string, unknown>;
  status?: string | null;
  cost_usd?: number | null;
  duration_ms?: number | null;
  error?: string | null;
  created_at?: string | null;
}

export interface AssistantRunDetail extends AssistantRunSummary {
  spec_version_id?: string | null;
  inputs?: Record<string, unknown>;
  output?: Record<string, unknown>;
  events?: AssistantRunEventEntry[];
}

export interface AssistantSkillSummary {
  slug: string;
  title: string;
  content_hash: string;
  path: string;
  tags: string[];
}

export interface AssistantHaltResponse {
  ok: boolean;
  halted_count: number;
  halted: Array<{ run_id?: string; task_id?: string | null; reason?: string }>;
}

export const AssistantsApi = {
  listSpecs: (): Promise<AssistantSpecSummary[]> =>
    apiFetch<AssistantSpecSummary[]>("/assistants"),

  getSpec: (name: string): Promise<AssistantSpecDetail> =>
    apiFetch<AssistantSpecDetail>(`/assistants/${encodeURIComponent(name)}`),

  createSession: (
    name: string,
    options?: { title?: string | null },
  ): Promise<AssistantSessionSummary> =>
    apiFetch<AssistantSessionSummary>(
      `/assistants/${encodeURIComponent(name)}/sessions`,
      {
        method: "POST",
        body: JSON.stringify({ title: options?.title ?? null }),
      },
    ),

  recentSessions: (params?: {
    limit?: number;
  }): Promise<AssistantSessionSummary[]> =>
    apiFetch<AssistantSessionSummary[]>(
      "/assistants/sessions/recent",
      params ? { query: params } : {},
    ),

  sendMessage: (
    name: string,
    prompt: string,
    options?: {
      session_id?: string | null;
      inputs?: Record<string, unknown>;
    },
  ): Promise<AssistantTaskResponse> =>
    apiFetch<AssistantTaskResponse>(
      `/assistants/${encodeURIComponent(name)}/messages`,
      {
        method: "POST",
        body: JSON.stringify({
          prompt,
          session_id: options?.session_id ?? null,
          inputs: options?.inputs ?? {},
        }),
      },
    ),

  listRuns: (params?: {
    assistant_spec_name?: string;
    status?: string;
    limit?: number;
  }): Promise<AssistantRunSummary[]> =>
    apiFetch<AssistantRunSummary[]>(
      "/assistants/runs",
      params ? { query: params } : {},
    ),

  getRun: (id: string): Promise<AssistantRunDetail> =>
    apiFetch<AssistantRunDetail>(
      `/assistants/runs/${encodeURIComponent(id)}`,
    ),

  listSkills: (): Promise<AssistantSkillSummary[]> =>
    apiFetch<AssistantSkillSummary[]>("/assistants/skills"),

  haltAll: (reason?: string): Promise<AssistantHaltResponse> =>
    apiFetch<AssistantHaltResponse>("/assistants/halt", {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? "user_halt" }),
    }),

  haltOne: (runId: string, reason?: string): Promise<AssistantHaltResponse> =>
    apiFetch<AssistantHaltResponse>("/assistants/halt", {
      method: "POST",
      body: JSON.stringify({ run_id: runId, reason: reason ?? "user_halt" }),
    }),
};
