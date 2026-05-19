/**
 * Workload Studio API client — drives `/manage/*` through the in-AQP
 * proxy installed by `aqp/api/proxy.py` (or directly to the
 * `aqp_control_plane` micro-project when run in client mode).
 *
 * Mirrors the shape of `aqp_platform_core.runtime.WorkloadRuntime`
 * so the SPA can stay provider-agnostic — docker_compose / kubernetes
 * / aws / azure / gcp / cloudflare all return the same envelope.
 */
import { apiFetch } from "./client";

export interface DeploymentStatus {
  service_id: string;
  provider: string;
  phase: string;
  replicas_desired: number;
  replicas_ready: number;
  image?: string | null;
  namespace?: string | null;
  last_transition_at?: string | null;
  conditions?: Array<Record<string, unknown>>;
  endpoints?: Record<string, string>;
  raw?: Record<string, unknown>;
}

export interface WorkloadExecResult {
  service_id: string;
  namespace?: string | null;
  container?: string | null;
  command: string[];
  stdout: string;
  stderr: string;
  returncode?: number | null;
  elapsed_ms?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface WorkloadLogEvent {
  service_id: string;
  namespace?: string | null;
  container?: string | null;
  line: string;
  timestamp?: string | null;
  source: string;
}

export interface ResponseEnvelope<T> {
  status: string;
  data: T;
  error?: { code: string; message: string; details?: Record<string, unknown> } | null;
}

export async function listDeployments(namespace?: string): Promise<DeploymentStatus[]> {
  const qs = namespace ? `?namespace=${encodeURIComponent(namespace)}` : "";
  const env = await apiFetch<ResponseEnvelope<DeploymentStatus[]>>(`/manage/deployments${qs}`);
  return env.data ?? [];
}

export async function getDeployment(
  serviceId: string,
  namespace?: string,
): Promise<DeploymentStatus | null> {
  const qs = namespace ? `?namespace=${encodeURIComponent(namespace)}` : "";
  const env = await apiFetch<ResponseEnvelope<DeploymentStatus>>(
    `/manage/deployments/${encodeURIComponent(serviceId)}${qs}`,
  );
  return env.data ?? null;
}

export async function startDeployment(
  serviceId: string,
  spec: Record<string, unknown>,
): Promise<DeploymentStatus | null> {
  const env = await apiFetch<ResponseEnvelope<DeploymentStatus>>(
    `/manage/deployments/${encodeURIComponent(serviceId)}/start`,
    { method: "POST", body: JSON.stringify({ ...spec, service_id: serviceId }) },
  );
  return env.data ?? null;
}

export async function stopDeployment(
  serviceId: string,
  namespace?: string,
): Promise<DeploymentStatus | null> {
  const qs = namespace ? `?namespace=${encodeURIComponent(namespace)}` : "";
  const env = await apiFetch<ResponseEnvelope<DeploymentStatus>>(
    `/manage/deployments/${encodeURIComponent(serviceId)}/stop${qs}`,
    { method: "POST" },
  );
  return env.data ?? null;
}

export async function scaleDeployment(
  serviceId: string,
  replicas: number,
  namespace?: string,
): Promise<DeploymentStatus | null> {
  const params = new URLSearchParams({ replicas: String(replicas) });
  if (namespace) params.set("namespace", namespace);
  const env = await apiFetch<ResponseEnvelope<DeploymentStatus>>(
    `/manage/deployments/${encodeURIComponent(serviceId)}/scale?${params}`,
    { method: "PATCH" },
  );
  return env.data ?? null;
}

export async function restartDeployment(
  serviceId: string,
  namespace?: string,
): Promise<DeploymentStatus | null> {
  const qs = namespace ? `?namespace=${encodeURIComponent(namespace)}` : "";
  const env = await apiFetch<ResponseEnvelope<DeploymentStatus>>(
    `/manage/deployments/${encodeURIComponent(serviceId)}/restart${qs}`,
    { method: "POST" },
  );
  return env.data ?? null;
}

/**
 * Halt every in-flight workload_runs row on the active control plane.
 * Wired into the topbar KillSwitch (Phase B of the Management Engine
 * plan).
 */
export async function haltAllWorkloads(): Promise<{ halted: number }> {
  return apiFetch<{ halted: number }>("/workloads/halt", { method: "POST" });
}

export async function execInDeployment(
  serviceId: string,
  payload: {
    command: string[];
    container?: string;
    timeout_seconds?: number;
    stdin_b64?: string;
    namespace?: string;
  },
): Promise<WorkloadExecResult | null> {
  const env = await apiFetch<ResponseEnvelope<WorkloadExecResult>>(
    `/manage/deployments/${encodeURIComponent(serviceId)}/exec`,
    { method: "POST", body: JSON.stringify(payload) },
  );
  return env.data ?? null;
}
