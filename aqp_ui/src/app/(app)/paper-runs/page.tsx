"use client";

import Link from "next/link";
import { Tag, Table } from "antd";
import { useQuery } from "@tanstack/react-query";

interface PaperRun {
  task_id: string;
  strategy_id: string;
  strategy_name: string;
  status: "running" | "completed" | "halted" | "errored";
  started_at: string;
  pnl?: number;
}

const STATUS_COLOR: Record<PaperRun["status"], string> = {
  running: "blue",
  completed: "green",
  halted: "warning",
  errored: "red",
};

export default function PaperRunsPage() {
  const { data, isLoading } = useQuery<{ runs: PaperRun[] }>({
    queryKey: ["paper-runs"],
    queryFn: async () => {
      const res = await fetch("/api/paper/runs", { credentials: "include" });
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
  });

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Paper runs
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Live paper-trading runs streaming through the canonical{" "}
          <code>/chat/stream/&#123;task_id&#125;</code> WebSocket.
        </p>
      </div>

      <Table
        rowKey="task_id"
        loading={isLoading}
        dataSource={data?.runs ?? []}
        columns={[
          {
            title: "Run",
            dataIndex: "task_id",
            render: (id: string, row: PaperRun) => (
              <Link href={`/paper-runs/${id}`} style={{ color: "var(--accent-primary)" }}>
                {row.strategy_name}{" "}
                <span style={{ color: "var(--text-muted)" }}>· {id.slice(0, 8)}</span>
              </Link>
            ),
          },
          {
            title: "Status",
            dataIndex: "status",
            render: (status: PaperRun["status"]) => (
              <Tag color={STATUS_COLOR[status]}>{status}</Tag>
            ),
          },
          { title: "Started", dataIndex: "started_at" },
          {
            title: "PnL",
            dataIndex: "pnl",
            render: (pnl?: number) =>
              pnl == null ? (
                <span style={{ color: "var(--text-muted)" }}>—</span>
              ) : (
                <span
                  data-numeric="true"
                  style={{ color: pnl >= 0 ? "var(--pos-fg)" : "var(--neg-fg)" }}
                >
                  {pnl >= 0 ? "+" : ""}
                  {pnl.toFixed(2)}%
                </span>
              ),
          },
        ]}
        pagination={{ pageSize: 25 }}
      />
    </div>
  );
}
