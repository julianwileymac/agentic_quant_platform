"use client";
import { Card, Space, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { AgentsApi, type AgentEvaluation } from "@/lib/api/agents";

const { Title } = Typography;

export function AgentEvaluationsPage() {
  const [rows, setRows] = useState<AgentEvaluation[]>([]);
  useEffect(() => {
    AgentsApi.listEvaluations({ limit: 100 }).then(setRows).catch(() => undefined);
  }, []);
  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Title level={2}>Agent Evaluations</Title>
      <Card>
        <Table<AgentEvaluation>
          rowKey="id"
          dataSource={rows}
          pagination={{ pageSize: 25 }}
          columns={[
            { title: "Spec", dataIndex: "spec_name", key: "spec_name" },
            { title: "Set", dataIndex: "eval_set_name", key: "eval_set_name" },
            { title: "Cases", dataIndex: "n_cases", key: "n_cases", align: "right" },
            { title: "Passed", dataIndex: "n_passed", key: "n_passed", align: "right" },
            {
              title: "Pass rate",
              key: "pass_rate",
              align: "right",
              render: (_: unknown, r) => {
                const rate = r.n_cases ? (r.n_passed / r.n_cases) * 100 : 0;
                return <Tag color={rate >= 80 ? "green" : rate >= 50 ? "blue" : "red"}>{rate.toFixed(1)}%</Tag>;
              },
            },
            { title: "Started", dataIndex: "started_at", key: "started_at" },
            { title: "Completed", dataIndex: "completed_at", key: "completed_at" },
          ]}
        />
      </Card>
    </Space>
  );
}
