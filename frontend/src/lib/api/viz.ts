import { apiFetch } from "./client";

export interface SavedChart {
  id: string;
  name: string;
  description?: string;
  viz_kind: string;
  owner?: string;
  workspace_id?: string;
  thumbnail_url?: string | null;
  config?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export const vizApi = {
  list: (): Promise<SavedChart[]> => apiFetch<SavedChart[]>("/visualizations"),
  get: (id: string): Promise<SavedChart> =>
    apiFetch<SavedChart>(`/visualizations/${encodeURIComponent(id)}`),
};
