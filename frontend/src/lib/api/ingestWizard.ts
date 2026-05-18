import type { ComputeBackendKind, ComputeSpec } from "./engines";
import { apiFetch } from "./client";
import {
  sourcesApi,
  type SetupWizardStepResult,
  type SetupWizardView,
  type SourceSummary,
} from "./sources";

export type IngestWizardMode = "source" | "preset" | "template";
export type IngestCheckSeverity = "info" | "warn" | "error";
export type QueuePressure = "low" | "moderate" | "high";

export interface QueueSnapshot {
  workers_seen: number;
  active: number;
  reserved: number;
  scheduled: number;
  queued: number;
  total: number;
  ingestion_active: number;
  ingestion_reserved: number;
  ingestion_scheduled: number;
  ingestion_queued: number;
}

export interface DatasetPresetSummary {
  name: string;
  description: string;
  namespace: string;
  table: string;
  source_kind: string;
  ingestion_task: string;
  tags: string[];
  schedule_cron?: string | null;
  requires_api_key?: boolean;
  api_key_env_var?: string | null;
  setup_steps?: Array<Record<string, unknown>>;
  required_config?: Record<string, unknown>;
}

export interface LoadingTemplateSummary {
  id: string;
  title: string;
  description: string;
  endpoint: string;
  run_kind: string;
  default_payload: Record<string, unknown>;
  fields: Array<Record<string, unknown>>;
}

export interface IngestWizardBootstrapResponse {
  generated_at: string;
  sources: SourceSummary[];
  source_wizards: SetupWizardView[];
  dataset_presets: DatasetPresetSummary[];
  loading_templates: LoadingTemplateSummary[];
  service_health: {
    ok?: boolean;
    services?: Record<string, { ok?: boolean; [extra: string]: unknown }>;
    config?: Record<string, unknown>;
    [extra: string]: unknown;
  };
  compute_status: Record<string, unknown>;
  queue: QueueSnapshot;
}

export interface IngestImportProbe {
  raw_source_url?: string | null;
  uri?: string | null;
  reference_path?: string | null;
  timeout_s?: number;
}

export interface IngestWizardPreflightRequest {
  source_name?: string;
  source_wizard_step_id?: string;
  source_wizard_payload?: Record<string, unknown>;
  preset_name?: string;
  template_id?: string;
  template_overrides?: Record<string, unknown>;
  import_probe?: IngestImportProbe | null;
  required_credentials?: string[];
  run_service_health?: boolean;
  run_compute_status?: boolean;
  run_queue_snapshot?: boolean;
  run_source_probe?: boolean;
  run_template_dry_run?: boolean;
}

export interface IngestWizardPreflightCheck {
  check_id: string;
  ok: boolean;
  severity: IngestCheckSeverity;
  message: string;
  details: Record<string, unknown>;
}

export interface IngestWizardPreflightResponse {
  generated_at: string;
  ok: boolean;
  checks: IngestWizardPreflightCheck[];
  queue?: QueueSnapshot | null;
}

export interface IngestWizardRecommendRequest {
  source_name?: string;
  requested_backend?: ComputeBackendKind;
  estimated_rows?: number;
  estimated_bytes?: number;
  symbol_count?: number;
  desired_rpm?: number | null;
  schedule_cron?: string | null;
}

export interface Advisory {
  severity: IngestCheckSeverity;
  message: string;
  details: Record<string, unknown>;
}

export interface QueueRecommendation {
  pressure: QueuePressure;
  recommended_parallel_runs: number;
  recommended_spacing_seconds: number;
  rationale: string[];
}

export interface RateLimitRecommendation {
  source_name?: string | null;
  provider_rpm?: number | null;
  provider_daily?: number | null;
  desired_rpm?: number | null;
  recommended_rpm?: number | null;
  rationale: string[];
}

export interface IngestWizardRecommendResponse {
  generated_at: string;
  queue: QueueSnapshot;
  compute: ComputeSpec & {
    requested_backend: string;
    rationale: string[];
  };
  queue_strategy: QueueRecommendation;
  rate_limit: RateLimitRecommendation;
  advisories: Advisory[];
}

export interface SourceLaunchRequest {
  name: string;
  namespace: string;
  table: string;
  description?: string | null;
  domain?: string;
  medallion_layer?: string | null;
  tags?: string[];
  source_node?: string | null;
  source_kwargs?: Record<string, unknown>;
  transforms?: Array<Record<string, unknown>>;
  schedule_cron?: string | null;
  run_now?: boolean;
}

export interface SourceLaunchResponse {
  dataset_id: string;
  manifest_id: string;
  iceberg_identifier: string;
  run_id?: string | null;
  status: string;
}

export interface PresetLaunchRequest {
  symbols?: string[];
  extra_kwargs?: Record<string, unknown>;
}

export interface PresetLaunchResponse {
  task_id: string;
  preset: string;
  status: string;
}

export interface TemplateLaunchRequest {
  overrides?: Record<string, unknown>;
}

export interface TemplateLaunchResponse {
  template_id: string;
  endpoint: string;
  run_kind: string;
  task_id: string;
  stream_url: string;
}

export const ingestWizardApi = {
  bootstrap: (): Promise<IngestWizardBootstrapResponse> =>
    apiFetch<IngestWizardBootstrapResponse>("/ingest/wizard/bootstrap"),

  preflight: (payload: IngestWizardPreflightRequest): Promise<IngestWizardPreflightResponse> =>
    apiFetch<IngestWizardPreflightResponse>("/ingest/wizard/preflight", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  recommend: (payload: IngestWizardRecommendRequest): Promise<IngestWizardRecommendResponse> =>
    apiFetch<IngestWizardRecommendResponse>("/ingest/wizard/recommend", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  launchSource: (sourceName: string, body: SourceLaunchRequest): Promise<SourceLaunchResponse> =>
    sourcesApi.createDataset(sourceName, body),

  launchPreset: (presetName: string, body?: PresetLaunchRequest): Promise<PresetLaunchResponse> =>
    apiFetch<PresetLaunchResponse>(`/dataset-presets/${encodeURIComponent(presetName)}/ingest`, {
      method: "POST",
      body: JSON.stringify({
        symbols: body?.symbols,
        extra_kwargs: body?.extra_kwargs ?? {},
      }),
    }),

  launchTemplate: (templateId: string, body?: TemplateLaunchRequest): Promise<TemplateLaunchResponse> =>
    apiFetch<TemplateLaunchResponse>(`/pipelines/templates/${encodeURIComponent(templateId)}/run`, {
      method: "POST",
      body: JSON.stringify({
        overrides: body?.overrides ?? {},
        dry_run: false,
      }),
    }),

  getSourceWizard: (sourceName: string): Promise<SetupWizardView> =>
    sourcesApi.getSetupWizard(sourceName),

  runSourceWizardStep: (
    sourceName: string,
    body: { step_id: string; payload?: Record<string, unknown> },
  ): Promise<SetupWizardStepResult> => sourcesApi.runSetupWizardStep(sourceName, body),
};
