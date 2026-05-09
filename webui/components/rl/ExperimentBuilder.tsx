"use client";

import { App, Button, Card, Col, Form, Input, InputNumber, Row, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { apiFetch } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws";

import { RL_PALETTE } from "./palette";
import { serializeRLExperimentSpec } from "./serialize";

const { Text, Paragraph } = Typography;

export function ExperimentBuilder() {
  const { message } = App.useApp();
  const [name, setName] = useState("ppo-portfolio");
  const [universe, setUniverse] = useState("AAPL.NASDAQ,MSFT.NASDAQ,GOOGL.NASDAQ");
  const [start, setStart] = useState("2018-01-01");
  const [end, setEnd] = useState("2023-06-30");
  const [totalTimesteps, setTotalTimesteps] = useState(200_000);
  const [graph, setGraph] = useState<FlowGraph>({
    domain: "rl",
    version: 1,
    nodes: [],
    edges: [],
  });
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  function buildSpec() {
    const spec = serializeRLExperimentSpec(graph, name);
    spec.universe = { symbols: universe.split(/[,\s]+/).filter(Boolean) };
    spec.training = { total_timesteps: Number(totalTimesteps) || 100_000 };
    if (spec.env && spec.env.kwargs) {
      spec.env.kwargs = { ...spec.env.kwargs, start, end };
    }
    return spec;
  }

  async function saveAndRun() {
    try {
      const spec = buildSpec();
      const saveRes = await apiFetch<{ slug: string }>("/rl/specs", {
        method: "POST",
        body: JSON.stringify({ spec }),
      });
      message.success(`Saved spec ${saveRes.slug}`);
      const runRes = await apiFetch<{ task_id: string }>(
        `/rl/specs/${encodeURIComponent(saveRes.slug)}/run`,
        {
          method: "POST",
          body: JSON.stringify({ target: "train" }),
        },
      );
      setTaskId(runRes.task_id);
      message.success(`RL training queued (${runRes.task_id})`);
    } catch (err) {
      message.error(`Failed: ${(err as Error).message}`);
    }
  }

  return (
    <PageContainer
      title="Experiment builder"
      subtitle="Compose env + agent + ensembler + evaluation into one RLExperimentSpec; save, train, stream."
      extra={
        <Space>
          <Button type="primary" onClick={saveAndRun}>
            Save & train
          </Button>
        </Space>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={16} style={{ height: 700 }}>
          <Card size="small" styles={{ body: { padding: 0, height: 700 } }}>
            <WorkflowEditor palette={RL_PALETTE} value={graph} onChange={setGraph} domain="rl" />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card size="small" title="Spec metadata" style={{ marginBottom: 12 }}>
            <Form layout="vertical">
              <Form.Item label="Name">
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </Form.Item>
              <Form.Item label="Universe (comma-separated vt_symbols)">
                <Input value={universe} onChange={(e) => setUniverse(e.target.value)} />
              </Form.Item>
              <Form.Item label="Start">
                <Input value={start} onChange={(e) => setStart(e.target.value)} placeholder="YYYY-MM-DD" />
              </Form.Item>
              <Form.Item label="End">
                <Input value={end} onChange={(e) => setEnd(e.target.value)} placeholder="YYYY-MM-DD" />
              </Form.Item>
              <Form.Item label="Total timesteps">
                <InputNumber
                  value={totalTimesteps}
                  onChange={(v) => setTotalTimesteps(Number(v) || 100_000)}
                  style={{ width: "100%" }}
                />
              </Form.Item>
            </Form>
          </Card>
          {taskId ? (
            <Card size="small" title="Live stream">
              <Space direction="vertical" style={{ width: "100%" }}>
                <Tag color="blue">{stream.status}</Tag>
                <Paragraph copyable={{ text: taskId }} style={{ margin: 0 }}>
                  {taskId}
                </Paragraph>
                <pre
                  style={{
                    fontSize: 11,
                    maxHeight: 240,
                    overflow: "auto",
                    background: "var(--ant-color-bg-elevated)",
                    padding: 8,
                    borderRadius: 6,
                  }}
                >
                  {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") || "Waiting…"}
                </pre>
              </Space>
            </Card>
          ) : null}
        </Col>
      </Row>
    </PageContainer>
  );
}
