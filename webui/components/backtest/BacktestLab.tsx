"use client";

import { ArrowLeftOutlined, RocketOutlined } from "@ant-design/icons";
import { App, Alert, Button, Card, Col, Form, Input, Row, Select, Skeleton, Space, Typography } from "antd";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
  loading: () => <Skeleton active />,
});

const { Text, Paragraph } = Typography;

const DEFAULT_CONFIG = `# Pass either a strategy id or an inline strategy YAML/JSON
{
  "strategy": {
    "name": "ad_hoc",
    "asset_class": "equity",
    "symbols": ["SPY", "AAPL"],
    "signals": [{ "kind": "sma_cross", "fast": 10, "slow": 30 }],
    "sizing": { "kind": "equal_weight" }
  },
  "engine": "EventDrivenBacktester",
  "start": "2022-01-01",
  "end": "2024-12-31",
  "initial_cash": 100000
}
`;

interface SubmitResp {
  task_id: string;
  stream_url?: string;
}

export function BacktestLab() {
  const router = useRouter();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [config, setConfig] = useState<string>(DEFAULT_CONFIG);
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  async function submit() {
    const values = await form.validateFields();
    let parsed: unknown;
    try {
      parsed = JSON.parse(config);
    } catch (err) {
      message.error(`Config is not valid JSON: ${(err as Error).message}`);
      return;
    }
    try {
      const res = await apiFetch<SubmitResp>("/backtest/run", {
        method: "POST",
        body: JSON.stringify({ config: parsed, run_name: values.run_name || "ad_hoc" }),
      });
      setTaskId(res.task_id);
      message.success(`Backtest queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title={
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => router.push("/backtest")} />
          New backtest
        </Space>
      }
      subtitle="Submit a strategy config and stream live progress."
      extra={
        <Button type="primary" icon={<RocketOutlined />} onClick={submit}>
          Run
        </Button>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="Run metadata" size="small">
            <Form form={form} layout="vertical" initialValues={{ run_name: "ad_hoc" }}>
              <Form.Item
                label="Run name"
                name="run_name"
                rules={[{ required: true, message: "Required" }]}
              >
                <Input />
              </Form.Item>
              <Form.Item label="Engine" name="engine">
                <Select
                  defaultValue="EventDrivenBacktester"
                  options={[
                    { value: "EventDrivenBacktester", label: "Event Driven" },
                    { value: "VectorbtEngine", label: "Vectorbt" },
                    { value: "BacktestingPyEngine", label: "backtesting.py" },
                  ]}
                />
              </Form.Item>
            </Form>
          </Card>

          <Card title="Stream" size="small" style={{ marginTop: 16 }}>
            {!taskId ? (
              <Text type="secondary">Run a backtest to see progress here.</Text>
            ) : (
              <>
                <Paragraph copyable={{ text: taskId }}>Task: {taskId}</Paragraph>
                <Text type="secondary">Status: {stream.status}</Text>
                {stream.error ? (
                  <Alert type="error" message={stream.error} style={{ marginTop: 8 }} />
                ) : null}
                <pre
                  style={{
                    fontSize: 11,
                    maxHeight: 220,
                    overflow: "auto",
                    background: "var(--ant-color-bg-elevated)",
                    padding: 8,
                    borderRadius: 6,
                    marginTop: 8,
                  }}
                >
                  {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") ||
                    "Waiting for events…"}
                </pre>
              </>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="Config (JSON)" size="small">
            <div style={{ height: 480 }}>
              <MonacoEditor
                height="100%"
                defaultLanguage="json"
                value={config}
                onChange={(v) => setConfig(v ?? "")}
                theme="vs-dark"
                options={{
                  fontSize: 13,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                }}
              />
            </div>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
