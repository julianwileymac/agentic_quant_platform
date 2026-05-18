import { apiFetch } from "./client";

export interface ControlPlaneTarget {
  id: string;
  label: string;
  kind: string;
  namespace: string;
}

export interface ControlPlaneService {
  id: string;
  label: string;
  role: string;
  workload: string;
  app_label: string;
  container: string;
  image_key: string;
  port?: number | null;
  health_path: string;
  storage: string;
  restartable: boolean;
  logs_enabled: boolean;
  selector: string;
}

export interface ControlPlaneTopologyTarget extends ControlPlaneTarget {
  environment: string;
  cloud_provider: string;
  endpoints: Record<string, string>;
  auth: Record<string, unknown>;
  terraform: {
    stack_slug: string;
    environment_dir: string;
  };
  services: ControlPlaneService[];
}

export interface ControlPlaneTopology {
  version: number;
  targets: ControlPlaneTopologyTarget[];
  tooling: Record<string, unknown>;
}

export interface ControlPlaneIdentityStatus {
  provider: string;
  required: boolean;
  oidc_issuer: string;
  oidc_audience: string;
  oidc_client_id_configured: boolean;
  scim_enabled: boolean;
  scim_endpoint: string;
  scim_patch_supported: boolean;
}

export interface ControlPlaneStatus {
  target: string;
  available: boolean;
  adapter: Record<string, unknown>;
  pods: Array<Record<string, unknown>>;
  namespace: string;
  services: ControlPlaneService[];
}

export interface TaskAccepted {
  task_id: string;
  status: string;
  stream_url: string;
}

export const controlPlaneApi = {
  getTopology: (): Promise<ControlPlaneTopology> =>
    apiFetch("/control-plane/topology"),
  getIdentityStatus: (): Promise<ControlPlaneIdentityStatus> =>
    apiFetch("/control-plane/identity"),
  listTargets: (): Promise<ControlPlaneTarget[]> =>
    apiFetch("/control-plane/kubernetes/targets"),
  getTargetStatus: (target: string): Promise<ControlPlaneStatus> =>
    apiFetch(`/control-plane/kubernetes/targets/${encodeURIComponent(target)}/status`),
  deployTarget: (target: string): Promise<TaskAccepted> =>
    apiFetch(`/control-plane/kubernetes/targets/${encodeURIComponent(target)}/deploy`, {
      method: "POST",
    }),
  destroyTarget: (target: string): Promise<TaskAccepted> =>
    apiFetch(`/control-plane/kubernetes/targets/${encodeURIComponent(target)}/destroy`, {
      method: "POST",
    }),
  restartTarget: (target: string): Promise<Record<string, unknown>> =>
    apiFetch(`/control-plane/kubernetes/targets/${encodeURIComponent(target)}/restart`, {
      method: "POST",
    }),
  logs: (target: string, service = "aqp-api"): Promise<{ logs: string }> =>
    apiFetch(`/control-plane/kubernetes/targets/${encodeURIComponent(target)}/logs`, {
      query: { service },
    }),
};
