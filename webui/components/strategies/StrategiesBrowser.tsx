"use client";

import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Input, Space } from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DataGrid, strategyColumns } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import type { StrategySummary } from "@/lib/api/domains";

export function StrategiesBrowser() {
  const router = useRouter();
  const [filter, setFilter] = useState("");
  const list = useApiQuery<StrategySummary[]>({
    queryKey: ["strategies", "list"],
    path: "/strategies/",
    select: (raw) => (Array.isArray(raw) ? (raw as StrategySummary[]) : []),
  });

  return (
    <PageContainer
      title="Strategies"
      subtitle="Versioned strategy catalog. Edit a strategy or kick off a backtest."
      extra={
        <Space>
          <Input.Search
            placeholder="Filter strategies"
            allowClear
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: 280 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => list.refetch()}>
            Refresh
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => router.push("/strategies/new")}
          >
            New strategy
          </Button>
        </Space>
      }
    >
      <DataGrid<StrategySummary>
        rowData={list.data ?? []}
        columnDefs={strategyColumns}
        loading={list.isLoading}
        quickFilterText={filter}
        getRowId={(r) => r.id}
        onRowClicked={(row) => router.push(`/strategies/${row.id}`)}
        height="calc(100vh - 220px)"
      />
    </PageContainer>
  );
}
