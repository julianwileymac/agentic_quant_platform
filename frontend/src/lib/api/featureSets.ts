import { apiFetch } from "./client";
import { useApiQuery } from "./hooks";

export interface FeatureSetSummary {
  id: string;
  name: string;
  description?: string | null;
  kind: string;
  specs: string[];
  default_lookback_days: number;
  tags: string[];
  version: number;
  status: string;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeatureSetUsageRow {
  id: string;
  feature_set_id: string;
  version?: number | null;
  consumer_kind: string;
  consumer_id?: string | null;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface FeatureSetVersionRow {
  id: string;
  version: number;
  specs: string[];
  notes?: string | null;
  created_by?: string | null;
  created_at: string;
}

export interface FeatureSetPreviewResp {
  feature_set_id?: string;
  name?: string;
  version?: number;
  specs?: string[];
  columns: string[];
  feature_columns?: string[];
  rows: Record<string, unknown>[];
  n_rows: number;
  warning?: string;
}

export const featureSetsApi = {
  list: () => apiFetch<FeatureSetSummary[]>("/feature-sets"),
  get: (id: string) =>
    apiFetch<FeatureSetSummary>(`/feature-sets/${encodeURIComponent(id)}`),
  versions: (id: string) =>
    apiFetch<FeatureSetVersionRow[]>(`/feature-sets/${encodeURIComponent(id)}/versions`),
  usages: (id: string) =>
    apiFetch<FeatureSetUsageRow[]>(`/feature-sets/${encodeURIComponent(id)}/usages`),
  preview: (id: string, params: Record<string, string | number | boolean | undefined> = {}) =>
    apiFetch<FeatureSetPreviewResp>(`/feature-sets/${encodeURIComponent(id)}/preview`, {
      query: params,
    }),
  create: (body: Partial<FeatureSetSummary>) =>
    apiFetch<FeatureSetSummary>("/feature-sets", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export function useFeatureSets() {
  return useApiQuery<FeatureSetSummary[]>({
    queryKey: ["feature-sets"],
    path: "/feature-sets",
    staleTime: 30_000,
  });
}

export function useFeatureSet(id: string | null | undefined) {
  return useApiQuery<FeatureSetSummary>({
    queryKey: ["feature-set", id ?? "_"],
    path: id ? `/feature-sets/${encodeURIComponent(id)}` : "/feature-sets/_disabled",
    enabled: Boolean(id),
  });
}

export function useFeatureSetVersions(id: string | null | undefined) {
  return useApiQuery<FeatureSetVersionRow[]>({
    queryKey: ["feature-set", id ?? "_", "versions"],
    path: id
      ? `/feature-sets/${encodeURIComponent(id)}/versions`
      : "/feature-sets/_/_disabled",
    enabled: Boolean(id),
  });
}

export function useFeatureSetUsages(id: string | null | undefined) {
  return useApiQuery<FeatureSetUsageRow[]>({
    queryKey: ["feature-set", id ?? "_", "usages"],
    path: id
      ? `/feature-sets/${encodeURIComponent(id)}/usages`
      : "/feature-sets/_/_disabled",
    enabled: Boolean(id),
  });
}
