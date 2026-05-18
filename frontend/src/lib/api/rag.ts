import { apiFetch } from "./client";

export interface RagCorpusInfo {
  name: string;
  order: string;
  l1: string;
  l2: string;
  iceberg?: string | null;
  description?: string;
  chunks?: number;
  last_indexed_at?: string | null;
}

export interface RagHit {
  doc_id: string;
  text: string;
  score: number;
  corpus: string;
  level?: string;
  order?: string;
  l1?: string;
  l2?: string;
  vt_symbol?: string;
  as_of?: string;
  source_id?: string;
  chunk_idx?: number;
  meta?: Record<string, unknown>;
}

export interface RagQueryRequest {
  query: string;
  level?: string;
  corpus?: string;
  order?: string;
  l1?: string;
  l2?: string;
  vt_symbol?: string;
  k?: number;
  rerank?: boolean;
  compress?: boolean;
}

export interface RagWalkRequest {
  query: string;
  levels?: string[];
  orders?: string[];
  vt_symbol?: string;
  per_level_k?: number;
  final_k?: number;
  rerank?: boolean;
  compress?: boolean;
}

export interface RagHierarchy {
  orders: string[];
  categories: Record<string, Record<string, string[]>>;
}

export interface TaskAcceptedRag {
  task_id: string;
  stream_url?: string;
}

export const ragApi = {
  corpora: (): Promise<RagCorpusInfo[]> => apiFetch<RagCorpusInfo[]>("/rag/corpora"),
  hierarchy: (): Promise<RagHierarchy> => apiFetch<RagHierarchy>("/rag/hierarchy"),
  query: (req: RagQueryRequest): Promise<RagHit[]> =>
    apiFetch<RagHit[]>("/rag/query", { method: "POST", body: JSON.stringify(req) }),
  walk: (req: RagWalkRequest): Promise<RagHit[]> =>
    apiFetch<RagHit[]>("/rag/walk", { method: "POST", body: JSON.stringify(req) }),
  indexCorpus: (corpus: string, kwargs: Record<string, unknown> = {}): Promise<TaskAcceptedRag> =>
    apiFetch<TaskAcceptedRag>(`/rag/index/${encodeURIComponent(corpus)}`, {
      method: "POST",
      body: JSON.stringify(kwargs),
    }),
  refreshL0: (): Promise<TaskAcceptedRag> =>
    apiFetch<TaskAcceptedRag>("/rag/refresh-l0", { method: "POST" }),
  refreshHierarchy: (corpora?: string[]): Promise<TaskAcceptedRag> =>
    apiFetch<TaskAcceptedRag>("/rag/refresh-hierarchy", {
      method: "POST",
      body: JSON.stringify(corpora ?? null),
    }),
  raptor: (corpus: string): Promise<TaskAcceptedRag> =>
    apiFetch<TaskAcceptedRag>(`/rag/raptor/${encodeURIComponent(corpus)}`, { method: "POST" }),
};
