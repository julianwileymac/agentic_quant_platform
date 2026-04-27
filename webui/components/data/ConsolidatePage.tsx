"use client";

import {
  ExperimentOutlined,
  MergeCellsOutlined,
  ReloadOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";

import { ConsolidationDrawer } from "@/components/data/ConsolidationDrawer";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Text, Paragraph } = Typography;

interface NamespaceList {
  namespaces?: string[];
}

interface GroupingSuggestion {
  group_name: string;
  members: string[];
  reason?: string | null;
  score: number;
}

interface GroupingResponse {
  namespace: string | null;
  strategy: string;
  groups: GroupingSuggestion[];
  count: number;
}

export function ConsolidatePage() {
  const { message } = App.useApp();

  const namespaces = useApiQuery<NamespaceList>({
    queryKey: ["datasets", "namespaces", "consolidate"],
    path: "/datasets/namespaces",
    staleTime: 60_000,
  });

  const [namespace, setNamespace] = useState<string | null>(null);
  const [strategy, setStrategy] = useState<"heuristic" | "llm">("heuristic");
  const [minSize, setMinSize] = useState(2);
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<GroupingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [consolidateOpen, setConsolidateOpen] = useState(false);
  const [activeGroup, setActiveGroup] = useState<GroupingSuggestion | null>(null);

  async function propose() {
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const res = await apiFetch<GroupingResponse>("/datasets/grouping/propose", {
        method: "POST",
        body: JSON.stringify({
          namespace: namespace ?? undefined,
          strategy,
          min_group_size: minSize,
        }),
      });
      setResponse(res);
      message.success(`Found ${res.count} candidate group(s) using ${res.strategy}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function openConsolidate(group: GroupingSuggestion) {
    setActiveGroup(group);
    setConsolidateOpen(true);
  }

  return (
    <PageContainer
      title="Consolidate part-tables"
      subtitle="Merge Iceberg tables that were loaded as multiple parts back into the single tables they represent."
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => namespaces.refetch()}>
          Refresh namespaces
        </Button>
      }
    >
      <Card title="Discover groups" style={{ marginBottom: 16 }}>
        <Form layout="vertical">
          <Row gutter={16}>
            <Col xs={24} md={6}>
              <Form.Item label="Namespace">
                <Select
                  allowClear
                  value={namespace ?? undefined}
                  onChange={(v) => setNamespace(v ?? null)}
                  placeholder="all namespaces"
                  options={(namespaces.data?.namespaces ?? []).map((ns) => ({
                    value: ns,
                    label: ns,
                  }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label="Strategy">
                <Select
                  value={strategy}
                  onChange={(v) => setStrategy(v)}
                  options={[
                    {
                      value: "heuristic",
                      label: (
                        <Space>
                          <ExperimentOutlined />
                          <span>heuristic (regex)</span>
                        </Space>
                      ),
                    },
                    {
                      value: "llm",
                      label: (
                        <Space>
                          <RobotOutlined />
                          <span>llm-driven</span>
                        </Space>
                      ),
                    },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label="Min group size">
                <InputNumber
                  min={2}
                  max={200}
                  value={minSize}
                  onChange={(v) => setMinSize(Number(v ?? 2))}
                  style={{ width: "100%" }}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6} style={{ display: "flex", alignItems: "end" }}>
              <Button
                type="primary"
                onClick={propose}
                loading={loading}
                style={{ width: "100%" }}
              >
                Propose groups
              </Button>
            </Col>
          </Row>
        </Form>
        <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          The <Text code>heuristic</Text> strategy looks for common name suffixes such as{" "}
          <Text code>_part_2</Text>, <Text code>_chunk_05</Text>, <Text code>_2of3</Text>. The{" "}
          <Text code>llm</Text> strategy asks the configured LLM provider to suggest groupings
          based on the table identifiers; it falls back to heuristic on errors.
        </Paragraph>
      </Card>

      {error ? <Alert type="error" showIcon style={{ marginBottom: 12 }} message={error} /> : null}
      {loading ? <Spin /> : null}

      {response ? (
        response.groups.length === 0 ? (
          <Empty description="No groups suggested with the current parameters." />
        ) : (
          <Card
            title={`Suggested groups (${response.groups.length})`}
            extra={<Tag color="blue">{response.strategy}</Tag>}
          >
            <Table<GroupingSuggestion>
              size="small"
              rowKey="group_name"
              dataSource={response.groups}
              pagination={{ pageSize: 20 }}
              columns={[
                {
                  title: "Target",
                  dataIndex: "group_name",
                  key: "group_name",
                  render: (v: string) => <code>{v}</code>,
                },
                {
                  title: "Members",
                  dataIndex: "members",
                  key: "members",
                  render: (m: string[]) => (
                    <Space wrap size={4}>
                      {m.slice(0, 5).map((id) => (
                        <Tag key={id}>{id}</Tag>
                      ))}
                      {m.length > 5 ? (
                        <Text type="secondary">+{m.length - 5} more</Text>
                      ) : null}
                    </Space>
                  ),
                },
                {
                  title: "Reason",
                  dataIndex: "reason",
                  key: "reason",
                  ellipsis: true,
                  render: (v: string | null | undefined) => v ?? "—",
                },
                {
                  title: "Score",
                  dataIndex: "score",
                  key: "score",
                  width: 80,
                  render: (v: number) => v.toFixed(2),
                  sorter: (a, b) => a.score - b.score,
                },
                {
                  title: "Action",
                  key: "action",
                  width: 220,
                  render: (_v, row) => (
                    <Space>
                      <Button
                        size="small"
                        type="primary"
                        icon={<MergeCellsOutlined />}
                        onClick={() => openConsolidate(row)}
                      >
                        Consolidate ({row.members.length})
                      </Button>
                    </Space>
                  ),
                },
              ]}
              expandable={{
                expandedRowRender: (row) => (
                  <Space wrap size={4}>
                    {row.members.map((id) => (
                      <Tag key={id} color="default">
                        {id}
                      </Tag>
                    ))}
                  </Space>
                ),
              }}
            />
          </Card>
        )
      ) : null}

      <ConsolidationDrawer
        open={consolidateOpen}
        onClose={() => setConsolidateOpen(false)}
        members={activeGroup?.members ?? []}
        defaultTarget={activeGroup?.group_name}
        onCompleted={() => {
          // Re-propose so the just-merged group disappears from the list.
          if (response) propose();
        }}
      />
    </PageContainer>
  );
}
