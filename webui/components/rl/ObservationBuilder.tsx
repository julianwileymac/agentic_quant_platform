"use client";

import { App, Button, Card, Col, Empty, Row, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { apiFetch } from "@/lib/api/client";

import { RL_OBSERVATION_PALETTE } from "./palette";
import { RL_MODULE_PATHS, type BuildSpec } from "./serialize";

const { Text } = Typography;

interface ObservationPreviewResponse {
  feature_names: string[];
  output_shape: number[];
  samples: { step: number; obs?: number[]; error?: string }[];
}

export function ObservationBuilder() {
  const { message } = App.useApp();
  const [graph, setGraph] = useState<FlowGraph>({
    domain: "rl",
    version: 1,
    nodes: [],
    edges: [],
  });
  const [preview, setPreview] = useState<ObservationPreviewResponse | null>(null);
  const [running, setRunning] = useState(false);

  function buildStackedFromGraph(): BuildSpec {
    const firstNode = graph.nodes[0];
    if (graph.nodes.length === 1 && firstNode) {
      return {
        class: firstNode.data.kind,
        module_path: RL_MODULE_PATHS[firstNode.data.kind],
        kwargs: { ...(firstNode.data.params ?? {}) },
      };
    }
    const builders = graph.nodes.map((n) => ({
      class: n.data.kind,
      module_path: RL_MODULE_PATHS[n.data.kind],
      kwargs: { ...(n.data.params ?? {}) },
    }));
    return {
      class: "StackedObservationBuilder",
      module_path: RL_MODULE_PATHS.StackedObservationBuilder,
      kwargs: { builders },
    };
  }

  async function runPreview() {
    setRunning(true);
    try {
      const observation = buildStackedFromGraph();
      const res = await apiFetch<ObservationPreviewResponse>("/rl/lab/preview-observation", {
        method: "POST",
        body: JSON.stringify({
          observation,
          env_states: [
            { weights: [0.4, 0.3, 0.3], portfolio_value: 100000, feature_tables: {} },
            { weights: [0.5, 0.2, 0.3], portfolio_value: 100500, feature_tables: {} },
          ],
        }),
      });
      setPreview(res);
    } catch (err) {
      message.error(`Preview failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <PageContainer
      title="Observation builder"
      subtitle="Compose the observation vector from registered builders. Output shape and feature names are computed live."
      extra={
        <Button type="primary" loading={running} onClick={runPreview}>
          Preview observation
        </Button>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={14} style={{ height: 600 }}>
          <Card size="small" styles={{ body: { padding: 0, height: 600 } }}>
            <WorkflowEditor
              palette={RL_OBSERVATION_PALETTE}
              value={graph}
              onChange={setGraph}
              domain="rl"
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card size="small" title="Output shape" style={{ marginBottom: 12 }}>
            {!preview ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Run preview to inspect." />
            ) : (
              <Space direction="vertical">
                <Text>shape: <Tag color="blue">{JSON.stringify(preview.output_shape)}</Tag></Text>
                <Text>features: {preview.feature_names.length}</Text>
              </Space>
            )}
          </Card>
          <Card size="small" title="Feature names">
            {preview?.feature_names.length ? (
              <Space wrap size={[4, 4]}>
                {preview.feature_names.slice(0, 60).map((name, i) => (
                  <Tag key={`${name}-${i}`}>{name}</Tag>
                ))}
                {preview.feature_names.length > 60 ? (
                  <Tag color="orange">…+{preview.feature_names.length - 60} more</Tag>
                ) : null}
              </Space>
            ) : (
              <Text type="secondary">No feature names yet.</Text>
            )}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
