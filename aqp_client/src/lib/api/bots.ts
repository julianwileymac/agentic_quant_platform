import { apiFetch } from "./client";

/**
 * Typed REST wrappers for the `/bots` surface. Mirrors the legacy
 * webui/lib/api/bots.ts so route components stay terse. The
 * server-side `BotSpec` is a Pydantic model — we keep the spec field
 * loosely typed and lean on the backend for shape enforcement.
 */

/**
 * Phase 8 (hybrid agentic-RL) introduced ``rl_trading`` — a bot
 * whose lifecycle is driven by ``RLRuntime`` instead of the standard
 * engine factory. Backend ``BotSpec`` already accepts it; the
 * frontend type widens here so visual builder pickers compile.
 */
export type BotKind = "trading" | "research" | "rl_trading";

export interface BotSummary {
  id: string;
  name: string;
  slug?: string;
  kind: BotKind | string;
  description?: string | null;
  status: string;
  current_version?: number;
  project_id?: string | null;
  workspace_id?: string | null;
  annotations?: string[];
  created_at?: string;
  updated_at?: string;
  /** Convenience metrics surfaced by the list endpoint. */
  strategy?: string | null;
  last_run_at?: string | null;
  pnl_total?: number | null;
  sharpe?: number | null;
}

export interface BotDetail extends BotSummary {
  spec: Record<string, unknown>;
  spec_yaml?: string | null;
}

export interface BotVersionOut {
  id: string;
  bot_id: string;
  version: number;
  spec_hash: string;
  created_at: string;
  notes?: string | null;
}

export interface BotDeploymentOut {
  id: string;
  bot_id: string | null;
  version_id: string | null;
  target: string;
  status: string;
  task_id?: string | null;
  started_at: string;
  ended_at?: string | null;
  error?: string | null;
  result_summary: Record<string, unknown>;
}

export interface TaskAccepted {
  task_id: string;
  status?: string;
  stream_url?: string | null;
}

export interface BotsListParams {
  project_id?: string;
  kind?: BotKind;
  status_filter?: string;
  limit?: number;
}

function botPath(ref: string, suffix = ""): string {
  return `/bots/${encodeURIComponent(ref)}${suffix}`;
}

export const BotsApi = {
  list(params?: BotsListParams): Promise<BotSummary[]> {
    if (!params) return apiFetch<BotSummary[]>("/bots");
    return apiFetch<BotSummary[]>("/bots", {
      query: {
        project_id: params.project_id,
        kind: params.kind,
        status_filter: params.status_filter,
        limit: params.limit,
      },
    });
  },

  get(botRef: string): Promise<BotDetail> {
    return apiFetch<BotDetail>(botPath(botRef));
  },

  create(spec: Record<string, unknown>, projectId?: string): Promise<BotDetail> {
    return apiFetch<BotDetail>("/bots", {
      method: "POST",
      body: JSON.stringify({ spec, project_id: projectId }),
    });
  },

  update(
    botRef: string,
    body: { spec?: Record<string, unknown>; spec_yaml?: string; status?: string; description?: string },
  ): Promise<BotDetail> {
    return apiFetch<BotDetail>(botPath(botRef), {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  remove(botRef: string): Promise<void> {
    return apiFetch<void>(botPath(botRef), { method: "DELETE" });
  },

  versions(botRef: string, limit = 50): Promise<BotVersionOut[]> {
    return apiFetch<BotVersionOut[]>(botPath(botRef, "/versions"), { query: { limit } });
  },

  deployments(botRef: string, limit = 50): Promise<BotDeploymentOut[]> {
    return apiFetch<BotDeploymentOut[]>(botPath(botRef, "/deployments"), { query: { limit } });
  },

  backtest(
    botRef: string,
    body?: { run_name?: string; overrides?: Record<string, unknown> },
  ): Promise<TaskAccepted> {
    return apiFetch<TaskAccepted>(botPath(botRef, "/backtest"), {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
  },

  startPaper(
    botRef: string,
    body?: { run_name?: string; overrides?: Record<string, unknown> },
  ): Promise<TaskAccepted> {
    return apiFetch<TaskAccepted>(botPath(botRef, "/paper/start"), {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
  },

  stopPaper(botRef: string, taskId: string): Promise<{ task_id: string; bot: string; ok: boolean }> {
    return apiFetch(botPath(botRef, `/paper/stop/${encodeURIComponent(taskId)}`), {
      method: "POST",
    });
  },

  deploy(
    botRef: string,
    body?: { target?: string; overrides?: Record<string, unknown> },
  ): Promise<TaskAccepted> {
    return apiFetch<TaskAccepted>(botPath(botRef, "/deploy"), {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
  },

  halt(botRef: string): Promise<{ ok: boolean }> {
    return apiFetch(botPath(botRef, "/halt"), { method: "POST" });
  },

  chat(
    botRef: string,
    body: { prompt: string; session_id?: string; agent_role?: string; inputs?: Record<string, unknown> },
  ): Promise<TaskAccepted> {
    return apiFetch<TaskAccepted>(botPath(botRef, "/chat"), {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};
