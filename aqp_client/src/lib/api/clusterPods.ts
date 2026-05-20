/**
 * Typed REST client for `/cluster/pods/*` — pod inventory, exec, log
 * streaming, archive transfer. Backs the new `cluster-mgmt` Vite route
 * (Phase F of the Management Engine plan).
 *
 * Note: live log tail uses WebSocket `/cluster/pods/{ns}/{name}/logs/stream`
 * via the existing `useLiveStream` hook — this client is for the
 * one-shot HTTP endpoints + the exec command surface.
 */
import { apiFetch } from "./client";

export interface PodInfo {
  namespace: string;
  name: string;
  phase: string;
  node: string;
  pod_ip: string;
  started_at: string;
  containers: string[];
  labels: Record<string, string>;
}

export interface PodExecResult {
  namespace: string;
  name: string;
  container?: string | null;
  command: string[];
  stdout: string;
  stderr: string;
  returncode: number | null;
  elapsed_ms?: number | null;
}

export async function listPods(
  namespace: string,
  labelSelector?: string,
): Promise<PodInfo[]> {
  const qs = labelSelector
    ? `?label_selector=${encodeURIComponent(labelSelector)}`
    : "";
  return apiFetch<PodInfo[]>(
    `/cluster/pods/${encodeURIComponent(namespace)}${qs}`,
  );
}

export async function execInPod(
  namespace: string,
  podName: string,
  payload: {
    command: string[];
    container?: string;
    timeout_seconds?: number;
    stdin_b64?: string;
  },
): Promise<PodExecResult> {
  return apiFetch<PodExecResult>(
    `/cluster/pods/${encodeURIComponent(namespace)}/${encodeURIComponent(podName)}/exec`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function getPodArchive(
  namespace: string,
  podName: string,
  path: string,
  container?: string,
): Promise<Blob> {
  const params = new URLSearchParams({ path });
  if (container) params.set("container", container);
  // Note: apiFetch's JSON pipeline would mangle binary payloads —
  // hand-roll the fetch here to preserve raw bytes.
  const url = `/cluster/pods/${encodeURIComponent(namespace)}/${encodeURIComponent(podName)}/archive?${params}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`getPodArchive failed: ${res.status} ${res.statusText}`);
  }
  return res.blob();
}

export async function putPodArchive(
  namespace: string,
  podName: string,
  path: string,
  body: Blob,
  container?: string,
): Promise<{ ok: boolean }> {
  const params = new URLSearchParams({ path });
  if (container) params.set("container", container);
  const url = `/cluster/pods/${encodeURIComponent(namespace)}/${encodeURIComponent(podName)}/archive?${params}`;
  const res = await fetch(url, {
    method: "POST",
    body,
    credentials: "include",
    headers: { "Content-Type": "application/octet-stream" },
  });
  if (!res.ok) {
    throw new Error(`putPodArchive failed: ${res.status} ${res.statusText}`);
  }
  return { ok: true };
}
