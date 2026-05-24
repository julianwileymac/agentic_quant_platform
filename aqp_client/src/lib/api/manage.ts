/**
 * Typed client for the AQP control-plane (`aqp_control_plane`)
 * `/manage/*` route groups. Phase 3 of the AQP infra-expansion plan.
 *
 * Each helper hits the canonical admin surface: topology lookup,
 * streaming clusters (Strimzi + Redpanda), observability (Prometheus,
 * Grafana, Phoenix), lakehouse (Iceberg + Hudi), time-series
 * (QuestDB), and the consolidated data-plane explorer.
 *
 * The frontend reaches the control plane through the Auth0-secured
 * ingress at `/manage/*` (the AQP API gateway proxies it through to
 * the `aqp-cp` deployment in the `aqp-admin` namespace).
 */
import { apiFetch } from "./client";

export interface ManageEnvelope<T> {
  status: string;
  data: T;
}

export interface TopologyService {
  id: string;
  aliases?: string[];
  label: string;
  role: string;
  workload: string;
  app_label: string;
  cluster?: string;
  namespace?: string;
  port?: number | null;
  health_path?: string;
  storage?: string;
  restartable?: boolean;
  logs_enabled?: boolean;
  protocols?: Record<string, number>;
  endpoints?: Record<string, string>;
  selector?: string;
}

export interface TopologyTargetSummary {
  id: string;
  label: string;
  kind: string;
  namespace: string;
}

export interface TopologySnapshot {
  version: number;
  defaults: Record<string, unknown>;
  services: TopologyService[];
  targets?: Record<string, unknown>;
  active_target_id: string;
}

export interface ServiceHealth {
  service_id: string;
  namespace: string;
  status: string;
  replicas?: { desired?: number | null; ready?: number | null };
  error?: string;
  detail?: string;
}

export interface StreamingCluster {
  id: string;
  label: string;
  cluster?: string;
  namespace?: string;
  endpoints: Record<string, string>;
  protocols: Record<string, number>;
}

const MANAGE_BASE = "/manage";

export const ManageApi = {
  // ---- topology ----------------------------------------------------------
  topology: {
    snapshot: async (): Promise<ManageEnvelope<TopologySnapshot>> =>
      apiFetch(`${MANAGE_BASE}/topology`),

    listServices: async (filters?: {
      role?: string;
      cluster?: string;
    }): Promise<ManageEnvelope<TopologyService[]>> =>
      apiFetch(`${MANAGE_BASE}/topology/services`, {
        query: { role: filters?.role, cluster: filters?.cluster },
      }),

    describeService: async (
      serviceId: string,
    ): Promise<ManageEnvelope<TopologyService>> =>
      apiFetch(`${MANAGE_BASE}/topology/services/${encodeURIComponent(serviceId)}`),

    serviceHealth: async (
      serviceId: string,
    ): Promise<ManageEnvelope<ServiceHealth>> =>
      apiFetch(
        `${MANAGE_BASE}/topology/services/${encodeURIComponent(serviceId)}/health`,
      ),

    listTargets: async (): Promise<ManageEnvelope<{ active: string; targets: Record<string, TopologyTargetSummary> }>> =>
      apiFetch(`${MANAGE_BASE}/topology/targets`),
  },

  // ---- streaming ---------------------------------------------------------
  streaming: {
    listClusters: async (): Promise<ManageEnvelope<StreamingCluster[]>> =>
      apiFetch(`${MANAGE_BASE}/streaming/clusters`),

    describeCluster: async (
      clusterId: string,
    ): Promise<ManageEnvelope<TopologyService>> =>
      apiFetch(
        `${MANAGE_BASE}/streaming/clusters/${encodeURIComponent(clusterId)}`,
      ),

    clusterHealth: async (
      clusterId: string,
    ): Promise<ManageEnvelope<ServiceHealth>> =>
      apiFetch(
        `${MANAGE_BASE}/streaming/clusters/${encodeURIComponent(clusterId)}/health`,
      ),

    halt: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/streaming/halt`, { method: "POST" }),
  },

  // ---- observability -----------------------------------------------------
  observability: {
    prometheusQuery: async (
      query: string,
    ): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/observability/prometheus/query`, {
        query: { query },
      }),

    prometheusAlerts: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/observability/prometheus/alerts`),

    grafanaDashboards: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/observability/grafana/dashboards`),

    grafanaDatasources: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/observability/grafana/datasources`),

    phoenixProjects: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/observability/phoenix/projects`),

    otelHealth: async (): Promise<ManageEnvelope<ServiceHealth>> =>
      apiFetch(`${MANAGE_BASE}/observability/otel/health`),
  },

  // ---- lakehouse ---------------------------------------------------------
  lakehouse: {
    listClusters: async (): Promise<ManageEnvelope<TopologyService[]>> =>
      apiFetch(`${MANAGE_BASE}/lakehouse/clusters`),

    icebergNamespaces: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/lakehouse/iceberg/namespaces`),

    hudiTables: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/lakehouse/hudi/tables`),

    halt: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/lakehouse/halt`, { method: "POST" }),
  },

  // ---- time-series (QuestDB) --------------------------------------------
  timeseries: {
    questdbStatus: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/timeseries/questdb/status`),

    questdbTables: async (): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/timeseries/questdb/tables`),

    questdbPartitions: async (
      table: string,
    ): Promise<ManageEnvelope<unknown>> =>
      apiFetch(`${MANAGE_BASE}/timeseries/questdb/partitions`, {
        query: { table },
      }),
  },

  // ---- data-plane (consolidated explorer) -------------------------------
  dataPlane: {
    listServices: async (): Promise<ManageEnvelope<TopologyService[]>> =>
      apiFetch(`${MANAGE_BASE}/data-plane/services`),

    describeService: async (
      serviceId: string,
    ): Promise<ManageEnvelope<TopologyService>> =>
      apiFetch(
        `${MANAGE_BASE}/data-plane/services/${encodeURIComponent(serviceId)}`,
      ),

    serviceHealth: async (
      serviceId: string,
    ): Promise<ManageEnvelope<ServiceHealth>> =>
      apiFetch(
        `${MANAGE_BASE}/data-plane/services/${encodeURIComponent(serviceId)}/health`,
      ),
  },
};
