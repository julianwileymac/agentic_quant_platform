import { apiFetch } from "./client";

export interface CfpbComplaintRow {
  complaint_id: string;
  company: string;
  product: string | null;
  issue: string | null;
  state: string | null;
  date_received: string | null;
  has_narrative: boolean;
}

export const CfpbApi = {
  probe: () => apiFetch<{ ok: boolean; message: string; endpoint: string }>("/cfpb/probe"),
  search: (params: Record<string, string | number | boolean | undefined>) =>
    apiFetch<{ count: number; hits: unknown[] }>("/cfpb/search", { query: params }),
  ingest: (body: Record<string, unknown>) =>
    apiFetch<{ task_id: string; stream_url?: string }>("/cfpb/ingest", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  complaints: (params: Record<string, string | number | undefined>) =>
    apiFetch<CfpbComplaintRow[]>("/cfpb/complaints", { query: params }),
};

export const FdaApi = {
  probe: () => apiFetch<{ ok: boolean; message: string }>("/fda/probe"),
  search: (endpoint: string, params: Record<string, string | number | undefined>) =>
    apiFetch<{ count: number; results: unknown[] }>(`/fda/search/${endpoint}`, { query: params }),
  ingestApplications: (body: Record<string, unknown>) =>
    apiFetch<{ task_id: string; stream_url?: string }>("/fda/ingest/applications", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  ingestAdverse: (body: Record<string, unknown>) =>
    apiFetch<{ task_id: string; stream_url?: string }>("/fda/ingest/adverse-events", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  ingestRecalls: (body: Record<string, unknown>) =>
    apiFetch<{ task_id: string; stream_url?: string }>("/fda/ingest/recalls", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  applications: (params: Record<string, string | number | undefined>) =>
    apiFetch<unknown[]>("/fda/applications", { query: params }),
  recalls: (params: Record<string, string | number | undefined>) =>
    apiFetch<unknown[]>("/fda/recalls", { query: params }),
};

export const UsptoApi = {
  probe: () => apiFetch<{ ok: boolean; message: string }>("/uspto/probe"),
  ingestPatents: (body: Record<string, unknown>) =>
    apiFetch<{ task_id: string; stream_url?: string }>("/uspto/ingest/patents", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  ingestTrademarks: (body: Record<string, unknown>) =>
    apiFetch<{ task_id: string; stream_url?: string }>("/uspto/ingest/trademarks", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  ingestAssignments: (body: Record<string, unknown>) =>
    apiFetch<{ task_id: string; stream_url?: string }>("/uspto/ingest/assignments", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patents: (params: Record<string, string | number | undefined>) =>
    apiFetch<unknown[]>("/uspto/patents", { query: params }),
  trademarks: (params: Record<string, string | number | undefined>) =>
    apiFetch<unknown[]>("/uspto/trademarks", { query: params }),
  assignments: (params: Record<string, string | number | undefined>) =>
    apiFetch<unknown[]>("/uspto/assignments", { query: params }),
};
