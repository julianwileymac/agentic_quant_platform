"use client";
import { Card, Col, Row, Space, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { AgentsApi, type AgentSpecSummary } from "@/lib/api/agents";

const { Title, Paragraph, Text } = Typography;

export function AgentRegistryPage() {
  const [specs, setSpecs] = useState<AgentSpecSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    AgentsApi.listSpecs()
      .then((data) => setSpecs(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Title level={2}>Agent Registry</Title>
        <Paragraph>
          Every spec-driven agent registered in this platform — research,
          selection, trader, and analysis teams. Each spec has a
          hash-locked snapshot persisted in <Text code>agent_spec_versions</Text>.
        </Paragraph>
      </div>

      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Title level={5} style={{ margin: 0 }}>Total specs</Title>
            <Title level={2} style={{ margin: 0 }}>{specs.length}</Title>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Title level={5} style={{ margin: 0 }}>Research</Title>
            <Title level={2} style={{ margin: 0 }}>
              {specs.filter((s) => s.name.startsWith("research.")).length}
            </Title>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Title level={5} style={{ margin: 0 }}>Selection / Trader</Title>
            <Title level={2} style={{ margin: 0 }}>
              {specs.filter((s) => s.name.startsWith("selection.") || s.name.startsWith("trader.")).length}
            </Title>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Title level={5} style={{ margin: 0 }}>Analysis</Title>
            <Title level={2} style={{ margin: 0 }}>
              {specs.filter((s) => s.name.startsWith("analysis.")).length}
            </Title>
          </Card>
        </Col>
      </Row>

      {error && (
        <Card>
          <Text type="danger">{error}</Text>
        </Card>
      )}

      <Card>
        <Table<AgentSpecSummary>
          rowKey="name"
          loading={loading}
          dataSource={specs}
          columns={[
            { title: "Name", dataIndex: "name", key: "name" },
            { title: "Role", dataIndex: "role", key: "role" },
            {
              title: "Memory",
              dataIndex: "memory_kind",
              key: "memory_kind",
              render: (v) => <Tag>{v}</Tag>,
            },
            {
              title: "Tools",
              dataIndex: "n_tools",
              key: "n_tools",
              align: "right",
            },
            {
              title: "RAG",
              dataIndex: "n_rag_clauses",
              key: "n_rag_clauses",
              align: "right",
            },
            {
              title: "Hash",
              dataIndex: "snapshot_hash",
              key: "snapshot_hash",
              render: (v: string) => <Text code>{v.slice(0, 12)}</Text>,
            },
            {
              title: "Tags",
              dataIndex: "annotations",
              key: "annotations",
              render: (tags: string[]) => (
                <Space wrap>
                  {(tags ?? []).map((t) => (
                    <Tag key={t}>{t}</Tag>
                  ))}
                </Space>
              ),
            },
          ]}
          pagination={{ pageSize: 25 }}
        />
      </Card>
    </Space>
  );
}
