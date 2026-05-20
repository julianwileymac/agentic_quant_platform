import { apiFetch } from "./client";

export type BuilderFieldKind =
  | "string"
  | "url"
  | "secret"
  | "number"
  | "boolean"
  | "select"
  | "json"
  | "credential_ref";

export interface BuilderField {
  name: string;
  label: string;
  kind: BuilderFieldKind;
  description?: string;
  required?: boolean;
  default?: unknown;
  options?: string[];
  placeholder?: string;
}

export interface BuilderSection {
  key: string;
  title: string;
  description?: string;
  fields: BuilderField[];
  repeatable?: boolean;
}

export interface CdkSchemaResponse {
  sections: BuilderSection[];
}

export interface ManifestValidationResult {
  errors: string[];
  warnings: string[];
}

export interface ManifestDraftResult {
  yaml: string;
  validation: ManifestValidationResult;
}

export interface InferStreamsResponse {
  ok: boolean;
  error?: string;
  streams: Array<{
    name: string;
    fields?: Array<{ name: string; type: string }>;
    error?: string;
  }>;
  preview?: Record<string, unknown>;
}

export interface FetcherCodegenResponse {
  path: string;
  rendered?: string;
  diff?: string;
  would_write?: boolean;
  exists?: boolean;
  written?: boolean;
}

export interface BuilderState {
  metadata: { connector_id?: string; display_name?: string; docs_url?: string };
  auth: {
    auth_kind?: "none" | "bearer" | "header" | "query" | "basic";
    credential_ref?: string;
    auth_header_name?: string;
    auth_query_field?: string;
  };
  requester: {
    base_url?: string;
    method?: "GET" | "POST" | "PUT";
    default_headers?: Record<string, string>;
    default_params?: Record<string, string>;
    timeout_s?: number;
  };
  paginator: {
    paginator_kind?:
      | "none"
      | "page_increment"
      | "offset_increment"
      | "cursor_field"
      | "next_link_url";
    page_size?: number;
    page_param?: string;
    cursor_field?: string;
  };
  extractor: { record_path?: string };
  streams: Array<{
    name?: string;
    path?: string;
    primary_key?: string;
    cursor_field?: string;
  }>;
}

export const EMPTY_BUILDER_STATE: BuilderState = {
  metadata: { connector_id: "", display_name: "", docs_url: "" },
  auth: { auth_kind: "none", credential_ref: "" },
  requester: {
    base_url: "",
    method: "GET",
    default_headers: {},
    default_params: {},
    timeout_s: 30,
  },
  paginator: { paginator_kind: "none", page_size: 100, page_param: "page" },
  extractor: { record_path: "$" },
  streams: [{ name: "", path: "" }],
};

export const AirbyteBuilderApi = {
  cdkSchema: async (): Promise<CdkSchemaResponse> =>
    apiFetch<CdkSchemaResponse>("/airbyte/builder/cdk-schema"),

  manifestDraft: async (state: BuilderState): Promise<ManifestDraftResult> =>
    apiFetch<ManifestDraftResult>("/airbyte/builder/manifest/draft", {
      method: "POST",
      body: JSON.stringify({ state }),
    }),

  manifestValidate: async (state: BuilderState): Promise<ManifestValidationResult> =>
    apiFetch<ManifestValidationResult>("/airbyte/builder/manifest/validate", {
      method: "POST",
      body: JSON.stringify({ state }),
    }),

  streamsInfer: async (state: BuilderState): Promise<InferStreamsResponse> =>
    apiFetch<InferStreamsResponse>("/airbyte/builder/streams/infer", {
      method: "POST",
      body: JSON.stringify({ state }),
    }),

  codegenFetcher: async (
    state: BuilderState,
    args: { commit?: boolean } = {},
  ): Promise<FetcherCodegenResponse> =>
    apiFetch<FetcherCodegenResponse>("/airbyte/builder/codegen/fetcher", {
      method: "POST",
      body: JSON.stringify({ state, commit: args.commit ?? false }),
    }),

  getState: async (
    connectorId: string,
  ): Promise<{ connector_id: string; state: BuilderState; manifest_yaml?: string; aqp_fetcher_path?: string }> =>
    apiFetch(
      `/airbyte/builder/state/${encodeURIComponent(connectorId)}`,
    ),

  putState: async (
    connectorId: string,
    state: BuilderState,
  ): Promise<{ connector_id: string; saved: boolean; manifest_yaml: string }> =>
    apiFetch(`/airbyte/builder/state/${encodeURIComponent(connectorId)}`, {
      method: "PUT",
      body: JSON.stringify({ state }),
    }),
};
