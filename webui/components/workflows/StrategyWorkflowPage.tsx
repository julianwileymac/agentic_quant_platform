"use client";

import { App, Card, Col, Input, Row, Space, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { STRATEGY_PALETTE } from "@/components/flow/palettes";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import { serializeStrategy } from "@/components/flow/serializers";
import type { FlowGraph } from "@/components/flow/types";
import { apiFetch } from "@/lib/api/client";

const { Text } = Typography;

const ACCENTS: Record<string, string> = {
  Signal: "#10b981",
  Factor: "#a855f7",
  Rule: "#3b82f6",
  Sizing: "#3b82f6",
  Risk: "#ef4444",
  Portfolio: "#f59e0b",
  Execution: "#f59e0b",
};

const STARTER_GRAPH: FlowGraph = {
  domain: "strategy",
  version: 1,
  nodes: [
    {
      id: "sig-1",
      type: "aqp",
      position: { x: 80, y: 60 },
      data: {
        kind: "Signal",
        label: "SMA crossover",
        params: { kind: "sma_cross", fast: 10, slow: 30 },
      },
    },
    {
      id: "size-1",
      type: "aqp",
      position: { x: 360, y: 60 },
      data: { kind: "Sizing", label: "Equal weight", params: { kind: "equal_weight" } },
    },
    {
      id: "port-1",
      type: "aqp",
      position: { x: 640, y: 60 },
      data: { kind: "Portfolio", label: "Portfolio" },
    },
  ],
  edges: [
    { id: "e1", source: "sig-1", target: "size-1" },
    { id: "e2", source: "size-1", target: "port-1" },
  ],
};

export function StrategyWorkflowPage() {
  const { message } = App.useApp();
  const router = useRouter();
  const [name, setName] = useState("flow_strategy_v1");

  async function run(graph: FlowGraph) {
    if (!name.trim()) {
      message.warning("Strategy name is required");
      return;
    }
    const payload = serializeStrategy(graph, name.trim());
    try {
      const res = await apiFetch<{ id: string }>("/strategies/", {
        method: "POST",
        body: JSON.stringify({ ...payload, author: "webui-flow" }),
      });
      message.success(`Strategy created (${res.id})`);
      router.push(`/strategies/${res.id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Strategy composer"
      subtitle="Wire signals → factors → rules → sizing → risk → portfolio. Save as a versioned strategy."
      full
    >
      <Row gutter={16} style={{ padding: "0 16px 12px" }}>
        <Col span={24}>
          <Card size="small">
            <Space>
              <Text type="secondary">Strategy name</Text>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{ width: 320 }}
              />
            </Space>
          </Card>
        </Col>
      </Row>
      <div style={{ flex: 1, padding: "0 16px 16px" }}>
        <WorkflowEditor
          domain="strategy"
          paletteSections={STRATEGY_PALETTE}
          initialGraph={STARTER_GRAPH}
          accentByKind={ACCENTS}
          onRun={run}
        />
      </div>
    </PageContainer>
  );
}
