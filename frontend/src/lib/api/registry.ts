import { apiFetch } from "./client";
import { useApiQuery } from "./hooks";

export interface ParamSchema {
  name: string;
  annotation: string;
  type: string;
  default: unknown;
  required: boolean;
  enum: unknown[] | null;
  description?: string | null;
}

export interface ComponentSummary {
  alias: string;
  qualname: string;
  kind: string;
  module?: string | null;
  source?: string | null;
  category?: string | null;
  tags: string[];
  doc?: string | null;
  params: ParamSchema[];
}

export interface ComponentDetail extends ComponentSummary {
  full_doc?: string | null;
}

export interface RegistryKindList {
  kinds: { kind: string; count: number }[];
}

export interface RegistryKindFilters {
  source?: string | null;
  category?: string | null;
  tag?: string | null;
}

export const registryApi = {
  kinds: () => apiFetch<RegistryKindList>("/registry/kinds"),
  kind: (kind: string, filters?: RegistryKindFilters) =>
    apiFetch<ComponentSummary[]>(`/registry/${encodeURIComponent(kind)}`, {
      query: {
        source: filters?.source ?? undefined,
        category: filters?.category ?? undefined,
        tag: filters?.tag ?? undefined,
      },
    }),
  component: (kind: string, alias: string) =>
    apiFetch<ComponentDetail>(
      `/registry/${encodeURIComponent(kind)}/${encodeURIComponent(alias)}`,
    ),
};

export function useRegistryKinds() {
  return useApiQuery<RegistryKindList>({
    queryKey: ["registry", "kinds"],
    path: "/registry/kinds",
    staleTime: 60_000,
  });
}

export function useRegistryKind(
  kind: string | null | undefined,
  filters?: RegistryKindFilters,
) {
  const query = {
    source: filters?.source || undefined,
    category: filters?.category || undefined,
    tag: filters?.tag || undefined,
  };
  return useApiQuery<ComponentSummary[]>({
    queryKey: [
      "registry",
      "kind",
      kind ?? "_",
      query.source ?? "_",
      query.category ?? "_",
      query.tag ?? "_",
    ],
    path: kind ? `/registry/${encodeURIComponent(kind)}` : "/registry/_disabled",
    query,
    enabled: Boolean(kind),
    staleTime: 60_000,
  });
}

export function useRegistryComponent(
  kind: string | null | undefined,
  alias: string | null | undefined,
) {
  return useApiQuery<ComponentDetail>({
    queryKey: ["registry", "component", kind ?? "_", alias ?? "_"],
    path:
      kind && alias
        ? `/registry/${encodeURIComponent(kind)}/${encodeURIComponent(alias)}`
        : "/registry/_/_disabled",
    enabled: Boolean(kind && alias),
    staleTime: 60_000,
  });
}

/**
 * Build the `{class, module_path, kwargs}` build-spec consumed by
 * `aqp.core.registry.build_from_config` from a wizard form's values.
 */
export function buildSpec(
  component: ComponentDetail | undefined,
  values: Record<string, unknown>,
): { class: string; module_path?: string; kwargs: Record<string, unknown> } {
  if (!component) return { class: "", kwargs: {} };
  const moduleParts = component.qualname.split(".");
  moduleParts.pop();
  const modulePath = component.module ?? moduleParts.join(".") ?? undefined;
  const kwargs: Record<string, unknown> = {};
  for (const param of component.params) {
    const v = values[param.name];
    if (v === undefined || v === null || v === "") continue;
    kwargs[param.name] = v;
  }
  return {
    class: component.alias,
    ...(modulePath ? { module_path: modulePath } : {}),
    kwargs,
  };
}
