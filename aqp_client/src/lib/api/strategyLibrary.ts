import { apiFetch } from "./client";

/**
 * Typed REST wrappers for the three Phase A endpoints that back the
 * Alpha Factor Studio + Examples Library / Gallery (Phase F).
 */

export interface AlphaFormulaTemplate {
  name: string;
  formula: string;
  rationale: string;
  expected_horizon_bars?: number | null;
  expected_direction?: string | null;
  tags: string[];
}

export interface AlphaFormulaTemplatesResponse {
  items: AlphaFormulaTemplate[];
}

export type BundledExampleKind = "alpha_factor" | "rl_spec" | "agent_spec";

export interface BundledExample {
  kind: BundledExampleKind;
  name: string;
  slug: string;
  description?: string | null;
  source_path?: string | null;
  payload: Record<string, unknown>;
  tags: string[];
}

export interface ExamplesLibraryResponse {
  items: BundledExample[];
}

export type LibraryCorpus =
  | "alpha_factors"
  | "backtest_summaries"
  | "rl_trajectory_summaries";

export interface LibraryHit {
  doc_id: string;
  corpus: string;
  score: number;
  text: string;
  meta: Record<string, unknown>;
  source_id?: string | null;
  vt_symbol?: string | null;
  as_of?: string | null;
}

export interface LibraryQueryResponse {
  corpus: string;
  query: string | null;
  items: LibraryHit[];
}

export const StrategyLibraryApi = {
  alphaTemplates: () =>
    apiFetch<AlphaFormulaTemplatesResponse>(
      "/quant-agents/alpha-formula-templates",
    ),

  examples: () =>
    apiFetch<ExamplesLibraryResponse>("/quant-agents/examples"),

  libraryQuery: (corpus: LibraryCorpus, q: string = "", k: number = 12) =>
    apiFetch<LibraryQueryResponse>(`/quant-agents/library/${corpus}`, {
      query: { q, k },
    }),
};
