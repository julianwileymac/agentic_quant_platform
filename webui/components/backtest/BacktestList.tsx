"use client";

import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Input, Space } from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { backtestColumns, DataGrid } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import type { BacktestRunSummary } from "@/lib/api/domains";

interface RawRun {
  id: string;
  status: string;
  start?: string | null;
  end?: string | null;
  sharpe?: number | null;
  sortino?: number | null;
  max_drawdown?: number | null;
  total_return?: number | null;
  final_equity?: number | null;
  created_at?: string;
}

function adapt(rows: unknown): BacktestRunSummary[] {
  if (!Array.isArray(rows)) return [];
  return (rows as RawRun[]).map((r) => ({
    id: r.id,
    status: r.status,
    started_at: r.created_at ?? r.start ?? null,
    finished_at: r.end ?? null,
    metrics: {
      sharpe: r.sharpe ?? null,
      sortino: r.sortino ?? null,
      max_drawdown: r.max_drawdown ?? null,
      cagr: r.total_return ?? null,
      final_equity: r.final_equity ?? null,
    },
  }));
}

export function BacktestList() {
  const router = useRouter();
  const [filter, setFilter] = useState("");
  const list = useApiQuery<BacktestRunSummary[]>({
    queryKey: ["backtest", "runs"],
    path: "/backtest/runs",
    query: { limit: 100 },
    select: (raw) => adapt(raw),
  });

  return (
    <PageContainer
      title="Backtest runs"
      subtitle="Past, in-flight, and queued backtests"
      extra={
        <Space>
          <Input.Search
            placeholder="Filter runs"
            allowClear
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: 280 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => list.refetch()}>
            Refresh
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => router.push("/backtest/new")}>
            New backtest
          </Button>
        </Space>
      }
    >
      <DataGrid<BacktestRunSummary>
        rowData={list.data ?? []}
        columnDefs={backtestColumns}
        loading={list.isLoading}
        quickFilterText={filter}
        getRowId={(r) => r.id}
        onRowClicked={(row) => router.push(`/backtest/${row.id}`)}
        height="calc(100vh - 220px)"
      />
    </PageContainer>
  );
}
