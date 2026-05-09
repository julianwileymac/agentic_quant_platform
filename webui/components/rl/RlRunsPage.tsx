"use client";

import { Card, Skeleton, Table, Tag } from "antd";
import Link from "next/link";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

interface RLRunRow {
  id: string;
  spec_id: string | null;
  version_id: string | null;
  target: string;
  status: string;
  task_id: string | null;
  mlflow_run_id: string | null;
  checkpoint: string | null;
  mean_reward: number | null;
  sharpe: number | null;
  max_drawdown: number | null;
  final_value: number | null;
  total_return: number | null;
  started_at: string | null;
  ended_at: string | null;
}

const STATUS_COLOR: Record<string, string> = {
  running: "processing",
  completed: "success",
  error: "error",
  cancelled: "default",
};

export function RlRunsPage() {
  const { data, isLoading } = useApiQuery<{ runs: RLRunRow[] }>({
    queryKey: ["rl", "runs"],
    path: "/rl/runs",
    refetchInterval: 5_000,
  });

  return (
    <PageContainer title="RL runs" subtitle="Every train / evaluate / paper / replay invocation of RLRuntime.">
      <Card size="small">
        {isLoading ? (
          <Skeleton active />
        ) : (
          <Table
            size="small"
            rowKey="id"
            dataSource={data?.runs ?? []}
            pagination={{ pageSize: 25 }}
            columns={[
              {
                title: "Run id",
                dataIndex: "id",
                width: 280,
                render: (id: string) => (
                  <Link href={`/rl/runs/${id}`}>
                    <code>{id.slice(0, 12)}…</code>
                  </Link>
                ),
              },
              { title: "Target", dataIndex: "target", width: 120 },
              {
                title: "Status",
                dataIndex: "status",
                width: 120,
                render: (status: string) => <Tag color={STATUS_COLOR[status] ?? "default"}>{status}</Tag>,
              },
              {
                title: "Mean reward",
                dataIndex: "mean_reward",
                render: (v: number | null) => (v == null ? "—" : v.toFixed(4)),
              },
              {
                title: "Sharpe",
                dataIndex: "sharpe",
                render: (v: number | null) => (v == null ? "—" : v.toFixed(3)),
              },
              {
                title: "Max DD",
                dataIndex: "max_drawdown",
                render: (v: number | null) => (v == null ? "—" : v.toFixed(3)),
              },
              {
                title: "Final value",
                dataIndex: "final_value",
                render: (v: number | null) => (v == null ? "—" : v.toFixed(0)),
              },
              {
                title: "Total return",
                dataIndex: "total_return",
                render: (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(2)}%`),
              },
              { title: "Started", dataIndex: "started_at", width: 200 },
            ]}
          />
        )}
      </Card>
    </PageContainer>
  );
}
