import { apiFetch } from "./client";

export interface FetcherSummary {
  name: string;
  kind: "source" | "transform" | "sink";
  description: string;
  tags: string[];
  module?: string;
  class_name?: string;
}

export interface FetcherSchemaField {
  name: string;
  annotation: string;
  required: boolean;
  default: unknown;
}

export interface FetcherSchema {
  name: string;
  class_name: string;
  module: string;
  doc: string;
  fields: FetcherSchemaField[];
}

export const fetchersApi = {
  list: () => apiFetch<FetcherSummary[]>("/fetchers"),
  listSources: () => apiFetch<FetcherSummary[]>("/fetchers/sources"),
  listTransforms: () => apiFetch<FetcherSummary[]>("/fetchers/transforms"),
  listSinks: () => apiFetch<FetcherSummary[]>("/fetchers/sinks"),
  getSchema: (name: string) =>
    apiFetch<FetcherSchema>(`/fetchers/${encodeURIComponent(name)}/schema`),
  probe: (name: string, kwargs: Record<string, unknown>) =>
    apiFetch<{ name: string; ok: boolean; result?: unknown; error?: string }>(
      "/fetchers/probe",
      { method: "POST", body: JSON.stringify({ name, kwargs }) },
    ),
};
