"use client";
import { Button, Card, Col, Collapse, Descriptions, Row, Space, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { AgentsApi, type AgentRunV2Detail, type AgentRunV2Step } from "@/lib/api/agents";

const { Title, Text } = Typography;

interface Props {
  runId: string;
}

export function AgentRunDetailPage({ runId }: Props) {
  const [run, setRun] = useState<AgentRunV2Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    AgentsApi.getRun(runId)
      .then(setRun)
      .catch((e: Error) => setError(e.message));
  }, [runId]);

  const onReplay = async () => {
    setBusy(true);
    try {
      const r = await AgentsApi.replayRun(runId);
      setRun(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (error) return <Card><Text type="danger">{error}</Text></Card>;
  if (!run) return <Card>Loading run {runId}…</Card>;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        title={<><Title level={3} style={{ margin: 0 }}>Agent Run {run.id.slice(0, 12)}…</Title></>}
        extra={<Button type="primary" loading={busy} onClick={onReplay}>Replay</Button>}
      >
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="Spec">{run.spec_name}</Descriptions.Item>
          <Descriptions.Item label="Status">
            <Tag color={run.status === "completed" ? "green" : run.status === "error" ? "red" : "blue"}>{run.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Cost (USD)">{run.cost_usd?.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="Calls">{run.n_calls}</Descriptions.Item>
          <Descriptions.Item label="Tool calls">{run.n_tool_calls}</Descriptions.Item>
          <Descriptions.Item label="RAG hits">{run.n_rag_hits}</Descriptions.Item>
          <Descriptions.Item label="Started">{run.started_at}</Descriptions.Item>
          <Descriptions.Item label="Completed">{run.completed_at ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="Spec version" span={2}>
            <Text code>{run.spec_version_id ?? "—"}</Text>
          </Descriptions.Item>
          {run.error && (
            <Descriptions.Item label="Error" span={2}>
              <Text type="danger">{run.error}</Text>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="Inputs" size="small">
            <pre style={{ margin: 0, maxHeight: 240, overflow: "auto" }}>
              {JSON.stringify(run.inputs, null, 2)}
            </pre>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="Output" size="small">
            <pre style={{ margin: 0, maxHeight: 240, overflow: "auto" }}>
              {JSON.stringify(run.output, null, 2)}
            </pre>
          </Card>
        </Col>
      </Row>

      <Card title={`Steps (${run.steps.length})`}>
        <Table<AgentRunV2Step>
          rowKey="seq"
          dataSource={run.steps}
          pagination={false}
          size="small"
          columns={[
            { title: "#", dataIndex: "seq", key: "seq", width: 50 },
            { title: "Kind", dataIndex: "kind", key: "kind", render: (v) => <Tag>{v}</Tag>, width: 90 },
            { title: "Name", dataIndex: "name", key: "name" },
            { title: "Cost", dataIndex: "cost_usd", key: "cost", align: "right", render: (v: number) => v?.toFixed(4) ?? "-" },
            { title: "Duration ms", dataIndex: "duration_ms", key: "duration", align: "right", render: (v: number) => (v != null ? v.toFixed(1) : "-") },
            {
              title: "Error",
              dataIndex: "error",
              key: "error",
              render: (v) => (v ? <Tag color="red">{v}</Tag> : "-"),
            },
          ]}
          expandable={{
            expandedRowRender: (record) => (
              <Collapse defaultActiveKey={["o"]} ghost>
                <Collapse.Panel header="inputs" key="i">
                  <pre style={{ margin: 0 }}>{JSON.stringify(record.inputs, null, 2)}</pre>
                </Collapse.Panel>
                <Collapse.Panel header="output" key="o">
                  <pre style={{ margin: 0 }}>{JSON.stringify(record.output, null, 2)}</pre>
                </Collapse.Panel>
              </Collapse>
            ),
          }}
        />
      </Card>
    </Space>
  );
}
