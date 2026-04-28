"use client";
import { Button, Card, Form, Input, Space, Typography, message } from "antd";
import { useState } from "react";

import { AgentsApi, type AgentRunV2Detail } from "@/lib/api/agents";

const { Title, Paragraph } = Typography;

interface Props {
  specName: string;
  title: string;
  description?: string;
  defaultPrompt?: string;
}

export function AgentTeamConsole({ specName, title, description, defaultPrompt }: Props) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AgentRunV2Detail | null>(null);

  const onRun = async (values: Record<string, string>) => {
    setBusy(true);
    setResult(null);
    try {
      const inputs: Record<string, unknown> = {};
      if (values.vt_symbol) inputs.vt_symbol = values.vt_symbol;
      if (values.as_of) inputs.as_of = values.as_of;
      if (values.universe) inputs.universe = values.universe.split(",").map((s) => s.trim()).filter(Boolean);
      if (values.prompt) inputs.prompt = values.prompt;
      if (values.model_id) inputs.model_id = values.model_id;
      if (values.strategy_id) inputs.strategy_id = values.strategy_id;

      const res = await AgentsApi.runSpecSync(specName, inputs);
      setResult(res);
      message.success(`run ${res.id.slice(0, 12)} ${res.status}`);
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Title level={2}>{title}</Title>
        {description && <Paragraph>{description}</Paragraph>}
        <Paragraph type="secondary">Spec: <code>{specName}</code></Paragraph>
      </div>

      <Card title="Run">
        <Form layout="vertical" onFinish={onRun} initialValues={{ prompt: defaultPrompt }}>
          <Form.Item label="vt_symbol" name="vt_symbol">
            <Input placeholder="AAPL.NASDAQ" />
          </Form.Item>
          <Form.Item label="as_of" name="as_of">
            <Input placeholder="2026-04-27 (optional)" />
          </Form.Item>
          <Form.Item label="universe (comma-separated)" name="universe">
            <Input placeholder="AAPL.NASDAQ, MSFT.NASDAQ" />
          </Form.Item>
          <Form.Item label="model_id" name="model_id">
            <Input placeholder="alpha158_lgbm (optional)" />
          </Form.Item>
          <Form.Item label="strategy_id" name="strategy_id">
            <Input placeholder="momentum (optional)" />
          </Form.Item>
          <Form.Item label="prompt" name="prompt">
            <Input.TextArea rows={4} placeholder="Free-form instruction for the agent" />
          </Form.Item>
          <Form.Item>
            <Button htmlType="submit" type="primary" loading={busy}>
              Run synchronously
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {result && (
        <Card title={`Output — ${result.status}`}>
          <Paragraph>
            cost={result.cost_usd?.toFixed(4)} USD | calls={result.n_calls} | rag_hits={result.n_rag_hits}
          </Paragraph>
          <pre style={{ margin: 0, maxHeight: 400, overflow: "auto" }}>
            {JSON.stringify(result.output, null, 2)}
          </pre>
        </Card>
      )}
    </Space>
  );
}
