import { apiFetch, ApiError } from "./client";
import { getAccessToken, hasAuthBackend } from "@/lib/auth/tokenStore";
import { API_BASE_URL } from "./config";
import { getTenancyHeaders } from "@/store/tenancy";

/**
 * Typed wrappers for the Phase 2 multi-tenant upload + merge endpoints.
 * Kept in its own module so the legacy `datasets.ts` catalog client can
 * stay backward compatible while we layer on workspace-scoped uploads.
 */

export interface UploadResponse {
  dataset_id: string;
  catalog_id: string;
  status: string;
  storage_uri: string;
  backend: string;
  filename: string;
  iceberg_identifier: string;
  namespace: string;
  table_name: string;
  task_id: string | null;
  bytes_written: number;
  workspace_id: string | null;
  project_id: string | null;
}

export interface MergeRequest {
  right_dataset_id: string;
  on: string[];
  how?: "inner" | "left" | "right" | "outer";
  target_table?: string;
}

export interface MergeResponse {
  task_id: string;
  target_namespace?: string | null;
  target_table?: string | null;
}

/**
 * Multipart upload — `apiFetch` expects JSON bodies, so we go through a
 * thin custom wrapper that forwards tenancy + Authorization headers,
 * keeps the FormData body, and surfaces ApiError on non-2xx.
 */
export async function uploadDataset(
  file: File,
  meta: { dataset_name?: string; description?: string } = {},
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (meta.dataset_name) form.append("dataset_name", meta.dataset_name);
  if (meta.description) form.append("description", meta.description);

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...getTenancyHeaders(),
  };
  if (hasAuthBackend()) {
    const token = await getAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  const url = `${API_BASE_URL}/datasets/upload`;
  const response = await fetch(url, {
    method: "POST",
    headers,
    body: form,
    credentials: "omit",
  });

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.clone().json();
    } catch {
      try {
        body = await response.clone().text();
      } catch {
        body = null;
      }
    }
    const detail =
      (body as { detail?: string })?.detail ?? response.statusText ?? `HTTP ${response.status}`;
    throw new ApiError(response.status, String(detail), body);
  }
  return (await response.json()) as UploadResponse;
}

export const mergeDatasets = (
  leftDatasetId: string,
  body: MergeRequest,
): Promise<MergeResponse> =>
  apiFetch<MergeResponse>(`/datasets/${encodeURIComponent(leftDatasetId)}/merge`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
