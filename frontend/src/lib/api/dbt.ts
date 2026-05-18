import { apiFetch } from "./client";

export interface DbtProjectStatus {
  project_dir: string;
  profiles_dir: string;
  duckdb_path: string;
  export_dir: string;
  target: string;
  exists: boolean;
  dbt_project_yml: boolean;
  profiles_yml: boolean;
  artifacts?: Record<string, string | null>;
  files?: DbtFileSummary[];
}

export interface DbtFileSummary {
  path: string;
  size: number;
  modified_at: number;
  generated: boolean;
}

export interface DbtFileContent {
  path: string;
  content: string;
  generated: boolean;
}

export interface DbtModelSummary {
  unique_id: string;
  name?: string | null;
  alias?: string | null;
  schema?: string | null;
  resource_type?: string | null;
  original_file_path?: string | null;
  materialized?: string | null;
  tags?: string[];
  depends_on?: string[];
  columns?: string[];
}

export interface DbtCommandResult {
  command: string;
  success: boolean;
  exception?: string | null;
  models: DbtModelSummary[];
  run_results: Record<string, unknown>;
  artifacts: Record<string, string | null>;
}

export interface DbtExportResult {
  status: string;
  export: {
    files: string[];
    models: string[];
    sources: string[];
    exported_tables: string[];
    warnings: string[];
  };
}

export const dbtApi = {
  project: () => apiFetch<DbtProjectStatus>("/dbt/project"),
  bootstrap: (force = false) =>
    apiFetch<{ status: DbtProjectStatus; written: string[] }>("/dbt/project/bootstrap", {
      method: "POST",
      body: JSON.stringify({ force }),
    }),
  export: () =>
    apiFetch<DbtExportResult>("/dbt/export", {
      method: "POST",
      body: JSON.stringify({ include_dataset_models: true, include_platform_tables: true }),
    }),
  models: () => apiFetch<DbtModelSummary[]>("/dbt/models"),
  parse: () => apiFetch<DbtCommandResult>("/dbt/parse", { method: "POST", body: JSON.stringify({}) }),
  build: (select: string[]) =>
    apiFetch<DbtCommandResult>("/dbt/build", {
      method: "POST",
      body: JSON.stringify({ select }),
    }),
  latestRun: () => apiFetch<Record<string, unknown>>("/dbt/runs/latest"),
  files: () => apiFetch<DbtFileSummary[]>("/dbt/files"),
  readFile: (path: string) => apiFetch<DbtFileContent>("/dbt/files", { query: { path } }),
  writeFile: (path: string, content: string) =>
    apiFetch<{ path: string; size: number }>("/dbt/files", {
      method: "PUT",
      body: JSON.stringify({ path, content }),
    }),
};
