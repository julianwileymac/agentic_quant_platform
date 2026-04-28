"use client";
import { Card, Col, Row, Space, Statistic, Table, Tag, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AgentsApi, type AgentRunV2Summary, type AgentSpecSummary } from "@/lib/api/agents";

const { Title, Paragraph } = Typography;

export function AgentDashboardPage() {
  const [specs, setSpecs] = useState<AgentSpecSummary[]>([]);
  const [runs, setRuns] = useState<AgentRunV2Summary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    AgentsApi.listSpecs().then(setSpecs).catch((e: Error) => setError(e.message));
    AgentsApi.listRuns({ limit: 25 }).then(setRuns).catch(() => undefined);
  }, []);

  const totalCost = runs.reduce((sum, r) => sum + (r.cost_usd ?? 0), 0);
  const completed = runs.filter((r) => r.status === "completed").length;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Title level={2}>Agents</Title>
        <Paragraph>
          Spec-driven agents (Research / Selection / Trader / Analysis) wired
          to the hierarchical Redis RAG. Use the registry to inspect specs,
          the runs page for full traces, and evaluations for harness scores.
        </Paragraph>
      </div>

      {error && <Card><span style={{ color: "var(--ant-color-error)" }}>{error}</span></Card>}

      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="Registered specs" value={specs.length} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="Recent runs" value={runs.length} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="Completed" value={completed} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="Recent cost (USD)" value={totalCost.toFixed(4)} />
          </Card>
        </Col>
      </Row>

      <Card title="Latest runs">
        <Table<AgentRunV2Summary>
          rowKey="id"
          dataSource={runs}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "Spec", dataIndex: "spec_name", key: "spec_name" },
            {
              title: "Status",
              dataIndex: "status",
              key: "status",
              render: (s: string) => (
                <Tag color={s === "completed" ? "green" : s === "running" ? "blue" : s === "error" ? "red" : "default"}>{s}</Tag>
              ),
            },
            {
              title: "Cost",
              dataIndex: "cost_usd",
              key: "cost_usd",
              align: "right",
              render: (v: number) => v?.toFixed(4) ?? "-",
            },
            { title: "Calls", dataIndex: "n_calls", key: "n_calls", align: "right" },
            { title: "RAG hits", dataIndex: "n_rag_hits", key: "n_rag_hits", align: "right" },
            { title: "Started", dataIndex: "started_at", key: "started_at" },
            {
              title: "Trace",
              key: "actions",
              render: (_: unknown, r: AgentRunV2Summary) => (
                <Link href={`/agents/runs/${r.id}`}>open</Link>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
