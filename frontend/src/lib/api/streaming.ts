import { apiFetch } from "./client";

// ----- Kafka --------------------------------------------------------
export interface KafkaTopic {
  name: string;
  partitions: number;
  replication_factor: number;
  config: Record<string, string>;
  is_internal: boolean;
}

export interface ConsumerGroup {
  group_id: string;
  state: string;
  members: number;
  topics: string[];
}

export interface ConsumerLagPartition {
  topic: string;
  partition: number;
  low: number;
  high: number;
  committed: number;
  lag: number;
}

export interface ConsumerLag {
  group_id: string;
  partitions: ConsumerLagPartition[];
}

export interface TopicSampleMessage {
  topic: string;
  partition: number;
  offset: number;
  timestamp?: number | null;
  key?: string | null;
  value_preview?: string | null;
}

export const kafkaApi = {
  topics: (includeInternal = false) =>
    apiFetch<KafkaTopic[]>("/streaming/kafka/topics", {
      query: { include_internal: includeInternal },
    }),
  topic: (name: string) =>
    apiFetch<KafkaTopic>(`/streaming/kafka/topics/${encodeURIComponent(name)}`),
  createTopic: (body: {
    name: string;
    partitions: number;
    replication_factor: number;
    config?: Record<string, string>;
  }) =>
    apiFetch<KafkaTopic>("/streaming/kafka/topics", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteTopic: (name: string) =>
    apiFetch<void>(`/streaming/kafka/topics/${encodeURIComponent(name)}`, { method: "DELETE" }),
  sample: (name: string, limit = 100) =>
    apiFetch<TopicSampleMessage[]>(
      `/streaming/kafka/topics/${encodeURIComponent(name)}/messages`,
      { query: { limit } },
    ),
  produce: (name: string, body: { key?: string; value: Record<string, unknown> }) =>
    apiFetch<unknown>(`/streaming/kafka/topics/${encodeURIComponent(name)}/produce`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  consumerGroups: () => apiFetch<ConsumerGroup[]>("/streaming/kafka/consumer-groups"),
  consumerLag: (group: string) =>
    apiFetch<ConsumerLag>(`/streaming/kafka/consumer-groups/${encodeURIComponent(group)}/lag`),
  schemaSubjects: () =>
    apiFetch<Array<{ subject: string }>>("/streaming/kafka/schema-registry/subjects"),
  schemaLatest: (subject: string) =>
    apiFetch<{
      subject: string;
      id?: number | null;
      version?: number | null;
      schema?: string | null;
      schema_type: string;
    }>(`/streaming/kafka/schema-registry/subjects/${encodeURIComponent(subject)}/versions/latest`),
};

// Aliases used by some legacy components.
export type { KafkaTopic as KafkaTopicSummary };

// ----- Flink --------------------------------------------------------
export interface FlinkSessionJob {
  name: string;
  namespace: string;
  state?: string | null;
  parallelism?: number | null;
  job_id?: string | null;
  jar_uri?: string | null;
  entry_class?: string | null;
  args?: string[];
  raw?: Record<string, unknown>;
}

export interface FlinkJobOverview {
  jid: string;
  name: string;
  state: string;
  start_time?: number;
  end_time?: number;
  duration?: number;
  tasks?: Record<string, number>;
}

export interface FlinkClusterOverview {
  taskmanagers: number;
  slots_total: number;
  slots_available: number;
  jobs_running: number;
  jobs_finished: number;
  jobs_failed: number;
  jobs_cancelled: number;
  flink_version?: string;
  cluster_id?: string;
}

export const flinkApi = {
  clusterOverview: () =>
    apiFetch<FlinkClusterOverview>("/streaming/flink/cluster"),
  sessionJobs: (namespace?: string) =>
    apiFetch<FlinkSessionJob[]>(
      "/streaming/flink/sessionjobs",
      namespace ? { query: { namespace } } : {},
    ),
  sessionJob: (name: string, namespace?: string) =>
    apiFetch<FlinkSessionJob>(
      `/streaming/flink/sessionjobs/${encodeURIComponent(name)}`,
      namespace ? { query: { namespace } } : {},
    ),
  createSessionJob: (body: Record<string, unknown>) =>
    apiFetch<FlinkSessionJob>("/streaming/flink/sessionjobs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patchSessionJob: (name: string, body: Record<string, unknown>) =>
    apiFetch<FlinkSessionJob>(`/streaming/flink/sessionjobs/${encodeURIComponent(name)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteSessionJob: (name: string, namespace?: string) =>
    apiFetch<void>(`/streaming/flink/sessionjobs/${encodeURIComponent(name)}`, {
      method: "DELETE",
      ...(namespace ? { query: { namespace } } : {}),
    }),
  activateSessionJob: (name: string) =>
    apiFetch<FlinkSessionJob>(
      `/streaming/flink/sessionjobs/${encodeURIComponent(name)}/activate`,
      { method: "POST" },
    ),
  suspendSessionJob: (name: string) =>
    apiFetch<FlinkSessionJob>(
      `/streaming/flink/sessionjobs/${encodeURIComponent(name)}/suspend`,
      { method: "POST" },
    ),
  triggerSavepoint: (name: string) =>
    apiFetch<{ trigger_id: string }>(
      `/streaming/flink/sessionjobs/${encodeURIComponent(name)}/savepoint`,
      { method: "POST" },
    ),
  scaleSessionJob: (name: string, parallelism: number) =>
    apiFetch<FlinkSessionJob>(
      `/streaming/flink/sessionjobs/${encodeURIComponent(name)}/scale`,
      { method: "POST", query: { parallelism } },
    ),
  jobs: () => apiFetch<FlinkJobOverview[]>("/streaming/flink/jobs"),
  job: (id: string) =>
    apiFetch<Record<string, unknown>>(`/streaming/flink/jobs/${encodeURIComponent(id)}`),
  jobExceptions: (id: string) =>
    apiFetch<Record<string, unknown>>(
      `/streaming/flink/jobs/${encodeURIComponent(id)}/exceptions`,
    ),
  cancelJob: (jid: string) =>
    apiFetch<{ ok: boolean }>(`/streaming/flink/jobs/${encodeURIComponent(jid)}/cancel`, {
      method: "POST",
    }),
  factorExport: (body: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>("/streaming/flink/jobs/factor-export", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ----- Producers ----------------------------------------------------
export interface ProducerSummary {
  id: string;
  name: string;
  kind: string;
  runtime: string;
  display_name: string;
  description?: string | null;
  deployment_namespace?: string | null;
  deployment_name?: string | null;
  image?: string | null;
  topics: string[];
  config: Record<string, unknown>;
  desired_replicas: number;
  current_replicas: number;
  last_status: string;
  last_status_at?: string | null;
  last_error?: string | null;
  enabled: boolean;
  tags: string[];
}

export interface ProducerStatus {
  name: string;
  current_replicas: number;
  desired_replicas: number;
  ready: boolean;
  message: string;
  last_status: string;
  last_status_at?: string | null;
  details: Record<string, unknown>;
}

export interface ProducerLogs {
  name: string;
  pod?: string | null;
  lines: string[];
}

export const producersApi = {
  list: () => apiFetch<ProducerSummary[]>("/streaming/producers"),
  get: (name: string) =>
    apiFetch<ProducerSummary>(`/streaming/producers/${encodeURIComponent(name)}`),
  create: (body: Record<string, unknown>) =>
    apiFetch<ProducerSummary>("/streaming/producers", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patch: (name: string, body: Record<string, unknown>) =>
    apiFetch<ProducerSummary>(`/streaming/producers/${encodeURIComponent(name)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  delete: (name: string) =>
    apiFetch<void>(`/streaming/producers/${encodeURIComponent(name)}`, { method: "DELETE" }),
  start: (name: string, replicas?: number) =>
    apiFetch<ProducerStatus>(`/streaming/producers/${encodeURIComponent(name)}/start`, {
      method: "POST",
      body: JSON.stringify(replicas !== undefined ? { replicas } : {}),
    }),
  stop: (name: string) =>
    apiFetch<ProducerStatus>(`/streaming/producers/${encodeURIComponent(name)}/stop`, {
      method: "POST",
    }),
  scale: (name: string, replicas: number) =>
    apiFetch<ProducerStatus>(`/streaming/producers/${encodeURIComponent(name)}/scale`, {
      method: "POST",
      body: JSON.stringify({ replicas }),
    }),
  restart: (name: string) =>
    apiFetch<ProducerStatus>(`/streaming/producers/${encodeURIComponent(name)}/restart`, {
      method: "POST",
    }),
  status: (name: string) =>
    apiFetch<ProducerStatus>(`/streaming/producers/${encodeURIComponent(name)}/status`),
  logs: (name: string, tail = 200) =>
    apiFetch<ProducerLogs>(`/streaming/producers/${encodeURIComponent(name)}/logs`, {
      query: { tail },
    }),
  topics: (name: string) =>
    apiFetch<{ producer: string; topics: string[]; links: unknown[] }>(
      `/streaming/producers/${encodeURIComponent(name)}/topics`,
    ),
};
