"use client";

import { App, Button, Switch } from "antd";
import type { ICellRendererParams } from "ag-grid-community";

import { DataGrid, StatusBadgeCell } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

interface SourceRow {
  id: string;
  name: string;
  display_name: string;
  vendor?: string | null;
  kind: string;
  protocol: string;
  enabled: boolean;
  capabilities?: Record<string, unknown>;
  rate_limits?: Record<string, unknown>;
  credentials_ref?: string | null;
}

export function DataSources() {
  const { message } = App.useApp();
  const list = useApiQuery<SourceRow[]>({
    queryKey: ["sources", "list"],
    path: "/sources/",
    select: (raw) => (Array.isArray(raw) ? (raw as SourceRow[]) : []),
  });

  async function toggle(row: SourceRow) {
    try {
      await apiFetch(`/sources/${row.name}/enabled`, {
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
      const res = await apiFetch<{ ok: boolean; message?: string }>(`/sources/${row.name}/probe`, {
        method: "POST",
      });
      if (res.ok) message.success(`${row.display_name}: reachable`);
      else message.warning(`${row.display_name}: ${res.message ?? "unreachable"}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Sources registry"
      subtitle="All known data adapters (yfinance, Polygon, Alpaca, IBKR, FRED, SEC, GDelt, etc.)."
    >
      <DataGrid<SourceRow>
        rowData={list.data ?? []}
        loading={list.isLoading}
        columnDefs={[
          { field: "display_name", headerName: "Source", flex: 2, minWidth: 200 },
          { field: "vendor", headerName: "Vendor", width: 140 },
          { field: "kind", headerName: "Kind", width: 130, cellRenderer: StatusBadgeCell },
          { field: "protocol", headerName: "Protocol", width: 110 },
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
        height="calc(100vh - 220px)"
      />
    </PageContainer>
  );
}
