"use client";

import { App, Button, Card, Col, Form, Input, Row, Space, Typography } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { apiFetch } from "@/lib/api/client";

import { RL_ENV_PALETTE } from "./palette";
import { serializeRLExperimentSpec } from "./serialize";

const { Text } = Typography;

export function EnvironmentBuilder() {
  const { message } = App.useApp();
  const [name, setName] = useState("my-rl-env");
  const [graph, setGraph] = useState<FlowGraph>({
    domain: "rl",
    version: 1,
    nodes: [],
    edges: [],
  });
  const [savedSlug, setSavedSlug] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function saveSpec() {
    setSaving(true);
    try {
      const spec = serializeRLExperimentSpec(graph, name);
      const res = await apiFetch<{ slug: string; version_id: string | null }>("/rl/specs", {
        method: "POST",
        body: JSON.stringify({ spec }),
      });
      setSavedSlug(res.slug);
      message.success(`Spec saved as ${res.slug} (version ${res.version_id ?? "n/a"})`);
    } catch (err) {
      message.error(`Save failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageContainer
      title="Environment builder"
      subtitle="Compose data pipeline + env + observation + action + reward + termination into a saveable RLExperimentSpec."
      extra={
        <Space>
          <Form layout="inline">
            <Form.Item label="Spec name">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="env-name" />
            </Form.Item>
          </Form>
          <Button type="primary" onClick={saveSpec} loading={saving}>
            Save spec
          </Button>
        </Space>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={20} style={{ height: 700 }}>
          <Card size="small" styles={{ body: { padding: 0, height: 700 } }}>
            <WorkflowEditor
              palette={RL_ENV_PALETTE}
              value={graph}
              onChange={setGraph}
              domain="rl"
            />
          </Card>
        </Col>
        <Col xs={24} lg={4}>
          <Card size="small" title="Spec summary">
            <Space direction="vertical" style={{ width: "100%", fontSize: 12 }}>
              <Text>nodes: {graph.nodes.length}</Text>
              <Text>edges: {graph.edges.length}</Text>
              {savedSlug ? <Text type="success">saved: {savedSlug}</Text> : null}
            </Space>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
