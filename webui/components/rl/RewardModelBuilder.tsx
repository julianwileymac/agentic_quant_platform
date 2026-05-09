"use client";

import { App, Button, Card, Col, InputNumber, Row, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { apiFetch } from "@/lib/api/client";

import { RL_REWARD_PALETTE } from "./palette";
import { RL_MODULE_PATHS, type BuildSpec } from "./serialize";

const { Text } = Typography;

interface PreviewStep {
  step?: number;
  reward: number;
  decomposition: Record<string, number>;
}

const SAMPLE_TRAJECTORY = [
  {
    step: 0,
    state: { portfolio_value: 100000, peak: 100000 },
    next_state: { portfolio_value: 100500, peak: 100500 },
    info: { turnover: 0.05, drawdown: 0.0 },
  },
  {
    step: 1,
    state: { portfolio_value: 100500, peak: 100500 },
    next_state: { portfolio_value: 100200, peak: 100500 },
    info: { turnover: 0.02, drawdown: -0.003 },
  },
  {
    step: 2,
    state: { portfolio_value: 100200, peak: 100500 },
    next_state: { portfolio_value: 99800, peak: 100500 },
    info: { turnover: 0.04, drawdown: -0.007 },
  },
  {
    step: 3,
    state: { portfolio_value: 99800, peak: 100500 },
    next_state: { portfolio_value: 100400, peak: 100500 },
    info: { turnover: 0.03, drawdown: -0.001 },
  },
];

export function RewardModelBuilder() {
  const { message } = App.useApp();
  const [graph, setGraph] = useState<FlowGraph>({
    domain: "rl",
    version: 1,
    nodes: [],
    edges: [],
  });
  const [preview, setPreview] = useState<PreviewStep[]>([]);
  const [running, setRunning] = useState(false);

  function buildCompositeFromGraph(): BuildSpec {
    const terms = graph.nodes.map((n) => ({
      class: n.data.kind,
      module_path: RL_MODULE_PATHS[n.data.kind],
      kwargs: { ...(n.data.params ?? {}) },
    }));
    return {
      class: "CompositeReward",
      module_path: RL_MODULE_PATHS.CompositeReward,
      kwargs: { terms },
    };
  }

  async function runPreview() {
    setRunning(true);
    try {
      const reward = buildCompositeFromGraph();
      const res = await apiFetch<{ steps: PreviewStep[] }>(
        "/rl/lab/preview-reward",
        {
          method: "POST",
          body: JSON.stringify({ reward, trajectory: SAMPLE_TRAJECTORY }),
        },
      );
      setPreview(res.steps ?? []);
    } catch (err) {
      message.error(`Preview failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }

  const termNames = preview[0] ? Object.keys(preview[0].decomposition) : [];
  const decompCols = termNames.map((name) => ({
    title: name,
    dataIndex: ["decomposition", name],
    key: name,
    render: (val: number | undefined) => (typeof val === "number" ? val.toFixed(4) : "—"),
  }));

  return (
    <PageContainer
      title="Reward builder"
      subtitle="Drag reward terms onto the canvas, weight them, and preview the per-term decomposition over a synthetic trajectory."
      extra={
        <Space>
          <Button type="primary" loading={running} onClick={runPreview}>
            Preview reward
          </Button>
        </Space>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={14} style={{ height: 600 }}>
          <Card size="small" styles={{ body: { padding: 0, height: 600 } }}>
            <WorkflowEditor
              palette={RL_REWARD_PALETTE}
              value={graph}
              onChange={setGraph}
              domain="rl"
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="Composite weights" size="small" style={{ marginBottom: 12 }}>
            <Space direction="vertical" style={{ width: "100%" }}>
              {graph.nodes.length === 0 ? (
                <Text type="secondary">Drop terms onto the canvas to begin.</Text>
              ) : null}
              {graph.nodes.map((node) => (
                <Card key={node.id} size="small" type="inner" title={<Tag color="red">{node.data.kind}</Tag>}>
                  <Space size={8}>
                    <Text>weight</Text>
                    <InputNumber
                      step={0.05}
                      value={(node.data.params?.weight as number | undefined) ?? 1.0}
                      onChange={(value) => {
                        setGraph((prev) => ({
                          ...prev,
                          nodes: prev.nodes.map((n) =>
                            n.id === node.id
                              ? {
                                  ...n,
                                  data: {
                                    ...n.data,
                                    params: { ...(n.data.params ?? {}), weight: value ?? 1.0 },
                                  },
                                }
                              : n,
                          ),
                        }));
                      }}
                    />
                  </Space>
                </Card>
              ))}
            </Space>
          </Card>
          <Card title="Reward decomposition preview" size="small">
            {preview.length === 0 ? (
              <Text type="secondary">Hit &quot;Preview reward&quot; once you&apos;ve added terms.</Text>
            ) : (
              <Table
                size="small"
                dataSource={preview}
                rowKey={(row) => `${row.step}-${row.reward}`}
                pagination={false}
                columns={[
                  { title: "step", dataIndex: "step", key: "step" },
                  {
                    title: "reward",
                    dataIndex: "reward",
                    key: "reward",
                    render: (val: number) => val.toFixed(4),
                  },
                  ...decompCols,
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
