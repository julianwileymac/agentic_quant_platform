"use client";

import { ReloadOutlined } from "@ant-design/icons";
import { Button, Space } from "antd";

import { DataGrid, mlModelColumns } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import type { MlModelSummary } from "@/lib/api/domains";

export function MlModelsPage() {
  const list = useApiQuery<MlModelSummary[]>({
    queryKey: ["ml", "models"],
    path: "/ml/models",
    select: (raw) => (Array.isArray(raw) ? (raw as MlModelSummary[]) : []),
  });

  return (
    <PageContainer
      title="ML Models"
      subtitle="Trained, registered, and deployed Qlib-style ML models."
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => list.refetch()}>
            Refresh
          </Button>
        </Space>
      }
    >
      <DataGrid<MlModelSummary>
        rowData={list.data ?? []}
        loading={list.isLoading}
        columnDefs={mlModelColumns}
        height="calc(100vh - 200px)"
      />
    </PageContainer>
  );
}
