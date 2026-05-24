"use client";

import { Select, Spin } from "antd";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

/**
 * Whitelist-only entity selector bound to the upstream metadata cache.
 *
 * AGENTS rule 8: free-text inputs are reserved for descriptions and
 * queries — never for the names of datasets, namespaces, sink kinds,
 * Airbyte connectors, projects, credentials, broker_credentials, etc.
 *
 * Mirrors aqp_client/src/components/common/EntityPicker.tsx but
 * targets the BFF proxy at /api/cache/{kind} instead of the AQP
 * backend directly.
 */

export type CacheCategory =
  | "datasets"
  | "namespaces"
  | "sink_kinds"
  | "sink_names"
  | "airbyte_connectors"
  | "projects"
  | "credentials"
  | "dataset_kinds"
  | "organizations"
  | "teams"
  | "users"
  | "workspaces"
  | "labs"
  | "experiments"
  | "tests"
  | "agents"
  | "bots"
  | "rl_experiments"
  | "analysis_specs"
  | "resources"
  | "strategy_templates"
  | "terraform_workspaces"
  | "terraform_providers"
  | "terraform_stacks"
  | "cloud_providers"
  | "entra_tenants"
  | "k8s_namespaces"
  | "k8s_clusters"
  | "streaming_clusters"
  | "timeseries_databases"
  | "phoenix_projects"
  | "grafana_dashboards"
  | "lakehouse_tables"
  | "topology_services"
  | "broker_credentials"
  | "broker_providers"
  | "vector_indexes";

interface EntityPickerProps {
  kind: CacheCategory;
  value?: string | null;
  onChange?: (value: string | null) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Limit returned options; defaults to 50. */
  limit?: number;
  /** Filter results by prefix (server-side ZRANGEBYLEX). */
  prefix?: string;
}

interface CacheEntry {
  id: string;
  label?: string;
  description?: string;
}

export function EntityPicker({
  kind,
  value,
  onChange,
  placeholder,
  disabled = false,
  limit = 50,
  prefix,
}: EntityPickerProps) {
  const [search, setSearch] = useState(prefix ?? "");
  const debouncedSearch = useDebounced(search, 200);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["cache", kind, debouncedSearch, limit],
    queryFn: async () => {
      const url = new URL(`/api/cache/${kind}`, window.location.origin);
      url.searchParams.set("limit", String(limit));
      if (debouncedSearch) url.searchParams.set("prefix", debouncedSearch);
      const res = await fetch(url.toString(), { credentials: "include" });
      if (!res.ok) throw new Error(`cache fetch failed: ${res.status}`);
      return (await res.json()) as { entries: CacheEntry[] };
    },
    staleTime: 30_000,
  });

  return (
    <Select
      showSearch
      allowClear
      value={value ?? undefined}
      onChange={(v) => onChange?.(v ?? null)}
      onSearch={setSearch}
      placeholder={placeholder ?? `Select ${humanise(kind)}`}
      disabled={disabled}
      filterOption={false}
      notFoundContent={isLoading || isFetching ? <Spin size="small" /> : "No matches"}
      options={(data?.entries ?? []).map((entry) => ({
        value: entry.id,
        label: entry.label ?? entry.id,
      }))}
      style={{ width: "100%" }}
    />
  );
}

function humanise(kind: CacheCategory): string {
  return kind.replace(/_/g, " ");
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}
