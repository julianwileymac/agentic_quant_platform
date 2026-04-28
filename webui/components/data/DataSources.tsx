"use client";

import { App, Button, Switch, Tabs, Tag, Tooltip } from "antd";
import type { ICellRendererParams } from "ag-grid-community";
import { useState } from "react";

import { DataGrid, StatusBadgeCell } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { fetchersApi, type FetcherSummary } from "@/lib/api/fetchers";

interface SourceRow {
  id: string;
  name: string;
  display_name: string;
  vendor?: string | null;
  kind: string;
  kind_subtype?: string | null;
  protocol: string;
  enabled: boolean;
  capabilities?: Record<string, unknown>;
  rate_limits?: Record<string, unknown>;
  credentials_ref?: string | null;
  health_status?: string | null;
  last_probe_at?: string | null;
}

export function DataSources() {
  const { message } = App.useApp();
  const [activeTab, setActiveTab] = useState<string>("registry");

  const list = useApiQuery<SourceRow[]>({
    queryKey: ["sources", "list"],
    path: "/sources/",
    select: (raw) => (Array.isArray(raw) ? (raw as SourceRow[]) : []),
  });

  const fetchers = useApiQuery<FetcherSummary[]>({
    queryKey: ["fetchers", "all"],
    path: "/fetchers",
    select: (raw) => (Array.isArray(raw) ? (raw as FetcherSummary[]) : []),
    enabled: activeTab === "fetchers",
  });

  async function toggle(row: SourceRow) {
    try {
      await apiFetch(`/sources/${row.name}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !row.enabled }),
      });
      message.success(`${row.display_name}: ${!row.enabled ? "enabled" : "disabled"}`);
      list.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function probe(row: SourceRow) {
    try {
      const res = await apiFetch<{ ok: boolean; message?: string }>(`/sources/${row.name}/probe`);
      if (res.ok) message.success(`${row.display_name}: reachable`);
      else message.warning(`${row.display_name}: ${res.message ?? "unreachable"}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function probeFetcher(name: string) {
    try {
      const res = await fetchersApi.probe(name, {});
      if (res.ok) message.success(`${name}: probe ok`);
      else message.warning(`${name}: ${res.error ?? "unreachable"}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Sources registry"
      subtitle="All known data adapters: data_sources rows + engine fetcher catalog."
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: "registry",
            label: "Registry",
            children: (
              <DataGrid<SourceRow>
                rowData={list.data ?? []}
                loading={list.isLoading}
                columnDefs={[
                  { field: "display_name", headerName: "Source", flex: 2, minWidth: 200 },
                  { field: "vendor", headerName: "Vendor", width: 140 },
                  {
                    field: "kind",
                    headerName: "Kind",
                    width: 110,
                    cellRenderer: StatusBadgeCell,
                  },
                  {
                    field: "kind_subtype",
                    headerName: "Subtype",
                    width: 110,
                  },
                  { field: "protocol", headerName: "Protocol", width: 110 },
                  {
                    field: "rate_limits",
                    headerName: "Rate",
                    width: 130,
                    valueGetter: (p) => {
                      const rl = (p.data?.rate_limits ?? {}) as Record<string, unknown>;
                      const rpm = rl.requests_per_minute ?? rl.req_per_minute;
                      return rpm ? `${rpm} rpm` : "-";
                    },
                  },
                  {
                    field: "health_status",
                    headerName: "Health",
                    width: 110,
                    cellRenderer: (p: ICellRendererParams<SourceRow>) => {
                      const status = p.value ?? "unknown";
                      const color =
                        status === "ok"
                          ? "green"
                          : status === "error"
                          ? "red"
                          : "default";
                      return (
                        <Tooltip title={p.data?.last_probe_at ?? "no probe yet"}>
                          <Tag color={color}>{String(status)}</Tag>
                        </Tooltip>
                      );
                    },
                  },
                  {
                    field: "enabled",
                    headerName: "Enabled",
                    width: 110,
                    cellRenderer: (p: ICellRendererParams<SourceRow>) => (
                      <Switch
                        size="small"
                        checked={Boolean(p.value)}
                        onChange={() => p.data && toggle(p.data)}
                      />
                    ),
                  },
                  {
                    headerName: "Actions",
                    width: 130,
                    cellRenderer: (p: ICellRendererParams<SourceRow>) => (
                      <Button size="small" onClick={() => p.data && probe(p.data)}>
                        Probe
                      </Button>
                    ),
                  },
                ]}
                height="calc(100vh - 280px)"
              />
            ),
          },
          {
            key: "fetchers",
            label: "Fetcher catalog",
            children: (
              <DataGrid<FetcherSummary>
                rowData={fetchers.data ?? []}
                loading={fetchers.isLoading}
                columnDefs={[
                  { field: "name", headerName: "Alias", flex: 1.5, minWidth: 220 },
                  {
                    field: "kind",
                    headerName: "Kind",
                    width: 110,
                    cellRenderer: StatusBadgeCell,
                  },
                  { field: "description", headerName: "Description", flex: 2, minWidth: 240 },
                  {
                    field: "tags",
                    headerName: "Tags",
                    width: 200,
                    valueFormatter: (p) =>
                      Array.isArray(p.value) ? (p.value as string[]).join(", ") : "",
                  },
                  {
                    headerName: "Actions",
                    width: 140,
                    cellRenderer: (p: ICellRendererParams<FetcherSummary>) => (
                      <Button
                        size="small"
                        onClick={() => p.data && probeFetcher(p.data.name)}
                      >
                        Probe
                      </Button>
                    ),
                  },
                ]}
                height="calc(100vh - 280px)"
              />
            ),
          },
        ]}
      />
    </PageContainer>
  );
}
