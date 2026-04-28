"use client";
import { Card, Input, Select, Space, Table, Tag, Typography } from "antd";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AgentsApi, type AgentRunV2Summary } from "@/lib/api/agents";

const { Title } = Typography;

export function AgentRunsPage() {
  const [runs, setRuns] = useState<AgentRunV2Summary[]>([]);
  const [specName, setSpecName] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    AgentsApi.listRuns({ spec_name: specName, status, limit: 200 })
      .then(setRuns)
      .finally(() => setLoading(false));
  }, [specName, status]);

  const filtered = useMemo(() => {
    if (!filter) return runs;
    const f = filter.toLowerCase();
    return runs.filter(
      (r) => r.id.includes(f) || r.spec_name.toLowerCase().includes(f),
    );
  }, [runs, filter]);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Title level={2}>Agent Runs</Title>

      <Card>
        <Space wrap>
          <Input
            placeholder="Filter by id or spec…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            allowClear
            style={{ width: 280 }}
          />
          <Select
            placeholder="Spec"
            allowClear
            style={{ width: 220 }}
            options={[
              "research.news_miner",
              "research.equity",
              "research.universe",
              "selection.stock_selector",
              "trader.signal_emitter",
              "analysis.step",
              "analysis.run",
              "analysis.portfolio",
            ].map((v) => ({ value: v, label: v }))}
            value={specName}
            onChange={setSpecName}
          />
          <Select
            placeholder="Status"
            allowClear
            style={{ width: 140 }}
            options={["pending", "running", "completed", "rejected", "error"].map((v) => ({ value: v, label: v }))}
            value={status}
            onChange={setStatus}
          />
        </Space>
      </Card>

      <Card>
        <Table<AgentRunV2Summary>
          rowKey="id"
          loading={loading}
          dataSource={filtered}
          pagination={{ pageSize: 25 }}
          columns={[
            {
              title: "Run",
              dataIndex: "id",
              key: "id",
              render: (id: string) => <Link href={`/agents/runs/${id}`}>{id.slice(0, 12)}…</Link>,
            },
            { title: "Spec", dataIndex: "spec_name", key: "spec_name" },
            {
              title: "Status",
              dataIndex: "status",
              key: "status",
              render: (s: string) => <Tag color={s === "completed" ? "green" : s === "error" ? "red" : "blue"}>{s}</Tag>,
            },
            { title: "Cost", dataIndex: "cost_usd", key: "cost", align: "right", render: (v: number) => v?.toFixed(4) ?? "-" },
            { title: "Calls", dataIndex: "n_calls", key: "calls", align: "right" },
            { title: "RAG hits", dataIndex: "n_rag_hits", key: "rag", align: "right" },
            { title: "Started", dataIndex: "started_at", key: "started" },
            { title: "Completed", dataIndex: "completed_at", key: "completed" },
          ]}
        />
      </Card>
    </Space>
  );
}
