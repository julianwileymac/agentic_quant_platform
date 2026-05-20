import { apiFetch } from "./client";

export interface MemoryEpisode {
  id: string;
  role: string;
  vt_symbol: string | null;
  situation: string;
  lesson: string;
  outcome: number | null;
  meta: Record<string, unknown>;
  created_at: string | null;
}

export interface MemoryReflection {
  id: string;
  role: string;
  vt_symbol: string | null;
  lesson: string;
  outcome: number | null;
  meta: Record<string, unknown>;
  created_at: string | null;
}

export interface MemoryOutcome {
  id: string;
  decision_id: string;
  vt_symbol: string;
  raw_return: number | null;
  benchmark_return: number | null;
  excess_return: number | null;
  direction_correct: number | null;
  decision_at: string | null;
  outcome_at: string | null;
}

export const MemoryApi = {
  episodes: (params?: { role?: string; vt_symbol?: string; limit?: number }) =>
    apiFetch<MemoryEpisode[]>("/memory/episodes", params ? { query: params } : {}),
  writeEpisode: (body: {
    role: string;
    situation: string;
    lesson: string;
    outcome?: number | null;
    vt_symbol?: string | null;
    metadata?: Record<string, unknown>;
  }) =>
    apiFetch<MemoryEpisode>("/memory/episodes", { method: "POST", body: JSON.stringify(body) }),
  reflections: (params?: { role?: string; vt_symbol?: string; limit?: number }) =>
    apiFetch<MemoryReflection[]>("/memory/reflections", params ? { query: params } : {}),
  outcomes: (params?: { vt_symbol?: string; limit?: number }) =>
    apiFetch<MemoryOutcome[]>("/memory/outcomes", params ? { query: params } : {}),
  reflect: (body: Record<string, unknown> = {}) =>
    apiFetch<{ resolved: number; reflected: number }>("/memory/reflect/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
