import { apiFetch } from "./client";

export interface SourceSummary {
  name: string;
  display_name?: string;
  description?: string;
  kind?: string;
  protocol?: string;
  enabled?: boolean;
  last_probe_status?: "ok" | "error" | "unknown";
  last_probe_message?: string;
  last_probe_at?: string | null;
  metadata_version?: number;
  tags?: string[];
}

export interface ProbeResult {
  name: string;
  ok: boolean;
  message: string;
  details?: Record<string, unknown>;
}

export interface SetupWizardStepField {
  id?: string;
  key?: string;
  name?: string;
  label?: string;
  type?: string;
  required?: boolean;
  [extra: string]: unknown;
}

export interface SetupWizardStepView {
  id: string;
  label: string;
  prompt: string;
  optional?: boolean;
  fields: SetupWizardStepField[];
}

export interface SetupWizardView {
  source_key: string;
  display_name: string;
  description?: string;
  documentation_url?: string | null;
  steps: SetupWizardStepView[];
}

export interface SetupWizardStepResult {
  ok: boolean;
  message: string;
  details: Record<string, unknown>;
  next_step?: string | null;
}

export interface SourceImportProbeRequest {
  raw_source_url?: string | null;
  uri?: string | null;
  reference_path?: string | null;
  timeout_s?: number;
}

export interface SourceImportProbeResult {
  reachable: boolean;
  uri: string;
  message: string;
  source_url?: string | null;
  reference_path?: string | null;
  response_time_ms?: number | null;
}

export interface CredentialEntry {
  key: string;
  value: string;
  configured: boolean;
  used_by: string[];
}

export interface CredentialsResponse {
  env_file: string;
  credentials: CredentialEntry[];
}

function path(name: string, suffix = ""): string {
  return `/sources/${encodeURIComponent(name)}${suffix}`;
}

export const sourcesApi = {
  list: (enabledOnly = false): Promise<SourceSummary[]> =>
    apiFetch<SourceSummary[]>("/sources", { query: { enabled_only: enabledOnly } }),
  get: (name: string): Promise<SourceSummary> => apiFetch<SourceSummary>(path(name)),
  listSetupWizards: (): Promise<SetupWizardView[]> =>
    apiFetch<SetupWizardView[]>("/sources/wizards"),
  getSetupWizard: (name: string): Promise<SetupWizardView> =>
    apiFetch<SetupWizardView>(path(name, "/setup-wizard")),
  runSetupWizardStep: (
    name: string,
    body: { step_id: string; payload?: Record<string, unknown> },
  ): Promise<SetupWizardStepResult> =>
    apiFetch<SetupWizardStepResult>(path(name, "/setup-wizard"), {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listCredentials: (): Promise<CredentialsResponse> =>
    apiFetch<CredentialsResponse>("/sources/credentials"),
  probeImport: (body: SourceImportProbeRequest): Promise<SourceImportProbeResult> =>
    apiFetch<SourceImportProbeResult>("/sources/import/probe", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  toggle: (name: string, enabled: boolean): Promise<SourceSummary> =>
    apiFetch<SourceSummary>(path(name), {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
  probe: (name: string): Promise<ProbeResult> => apiFetch<ProbeResult>(path(name, "/probe")),
  edit: (name: string, body: Record<string, unknown>): Promise<SourceSummary> =>
    apiFetch<SourceSummary>(path(name), { method: "PUT", body: JSON.stringify(body) }),
  createDataset: (
    name: string,
    body: {
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
    },
  ): Promise<{
    dataset_id: string;
    manifest_id: string;
    iceberg_identifier: string;
    run_id?: string | null;
    status: string;
  }> =>
    apiFetch(path(name, "/datasets"), {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
