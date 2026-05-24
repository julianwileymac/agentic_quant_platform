"use client";

import Link from "next/link";
import { Button, Table } from "antd";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";

interface Strategy {
  id: string;
  name: string;
  kind: string;
  status: "draft" | "active" | "paused";
  updated_at: string;
}

export default function StrategiesPage() {
  const { data, isLoading } = useQuery<{ strategies: Strategy[] }>({
    queryKey: ["strategies"],
    queryFn: async () => {
      const res = await fetch("/api/strategies", { credentials: "include" });
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
            Strategies
          </h1>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            Hash-locked spec versions — each save creates an immutable revision.
          </p>
        </div>
        <Link href="/strategies/new">
          <Button type="primary" icon={<Plus size={14} />}>
            New strategy
          </Button>
        </Link>
      </div>

      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={data?.strategies ?? []}
        columns={[
          {
            title: "Name",
            dataIndex: "name",
            render: (name: string, row: Strategy) => (
              <Link href={`/strategies/${row.id}`} style={{ color: "var(--accent-primary)" }}>
                {name}
              </Link>
            ),
          },
          { title: "Kind", dataIndex: "kind" },
          { title: "Status", dataIndex: "status" },
          { title: "Last updated", dataIndex: "updated_at" },
        ]}
        pagination={{ pageSize: 25 }}
      />
    </div>
  );
}
