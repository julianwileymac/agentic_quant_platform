"use client";

import { App, Card, Col, Input, Row, Space, Typography } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { AGENT_PALETTE } from "@/components/flow/palettes";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import { serializeAgentCrew } from "@/components/flow/serializers";
import type { FlowGraph } from "@/components/flow/types";
import { apiFetch } from "@/lib/api/client";

const { Text } = Typography;

const ACCENTS: Record<string, string> = {
  LLM: "#10b981",
  Memory: "#a855f7",
  Tool: "#3b82f6",
  Agent: "#f59e0b",
  Task: "#8b5cf6",
  Output: "#ef4444",
};

const STARTER_GRAPH: FlowGraph = {
  domain: "agent",
  version: 1,
  nodes: [
    {
      id: "llm-1",
      type: "aqp",
      position: { x: 60, y: 60 },
      data: { kind: "LLM", label: "Deep model", params: { tier: "deep" } },
    },
    {
      id: "agent-1",
      type: "aqp",
      position: { x: 320, y: 60 },
      data: { kind: "Agent", label: "Researcher", params: { role: "researcher" } },
    },
    {
      id: "out-1",
      type: "aqp",
      position: { x: 600, y: 60 },
      data: { kind: "Output", label: "Final report" },
    },
  ],
  edges: [
    { id: "e1", source: "llm-1", target: "agent-1" },
    { id: "e2", source: "agent-1", target: "out-1" },
  ],
};

export function AgentWorkflowPage() {
  const { message } = App.useApp();
  const [prompt, setPrompt] = useState(
    "Research the SPY universe and produce a 1-page brief on momentum opportunities.",
  );

  async function run(graph: FlowGraph) {
    const payload = serializeAgentCrew(graph, prompt);
    const res = await apiFetch<{ task_id: string }>("/agents/crew/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    message.success(`Crew submitted (task ${res.task_id}). Open Crew Trace to follow it.`);
  }

  return (
    <PageContainer
      title="Agent Crew editor"
      subtitle="Visually compose CrewAI-style multi-agent pipelines."
      full
    >
      <Row gutter={16} style={{ padding: "0 16px 12px" }}>
        <Col span={24}>
          <Card size="small">
            <Space style={{ width: "100%" }} direction="vertical">
              <Text type="secondary">Top-level prompt sent with the crew</Text>
              <Input.TextArea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                autoSize={{ minRows: 1, maxRows: 4 }}
              />
            </Space>
          </Card>
        </Col>
      </Row>
      <div style={{ flex: 1 }}>
        <WorkflowEditor
          domain="agent"
          paletteSections={AGENT_PALETTE}
          initialGraph={STARTER_GRAPH}
          accentByKind={ACCENTS}
          onRun={run}
        />
      </div>
    </PageContainer>
  );
}
