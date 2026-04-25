"use client";

import { App, Button, Card, Col, Form, Input, InputNumber, Row, Select, Space, Tag, Typography } from "antd";
import dynamic from "next/dynamic";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
});

const { Paragraph, Text } = Typography;

const DEFAULT_CONFIG = `{
  "model": "lightgbm",
  "task": "regression",
  "features": ["alpha158"],
  "target": "next_5d_return",
  "universe": ["SPY", "AAPL", "MSFT", "GOOGL"],
  "train_start": "2018-01-01",
  "train_end": "2022-12-31",
  "test_start": "2023-01-01",
  "test_end": "2024-12-31"
}`;

export function MlTrainingPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  async function submit() {
    const v = await form.validateFields();
    let parsed: unknown;
    try {
      parsed = JSON.parse(config);
    } catch (err) {
      message.error(`Config not valid JSON: ${(err as Error).message}`);
      return;
    }
    try {
      const res = await apiFetch<{ task_id: string }>("/ml/train", {
        method: "POST",
        body: JSON.stringify({ config: parsed, run_name: v.run_name }),
      });
      setTaskId(res.task_id);
      message.success(`Training queued (${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer title="ML Training" subtitle="Submit a Qlib-style ML pipeline and stream progress.">
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="Run" size="small">
            <Form form={form} layout="vertical" initialValues={{ run_name: "lgbm_alpha158", n_seeds: 1 }}>
              <Form.Item label="Run name" name="run_name" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item label="Seeds" name="n_seeds">
                <InputNumber min={1} max={10} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item label="Compute" name="compute">
                <Select
                  defaultValue="cpu"
                  options={[
                    { value: "cpu", label: "CPU (default)" },
                    { value: "gpu", label: "GPU (training queue)" },
                  ]}
                />
              </Form.Item>
              <Button type="primary" onClick={submit}>
                Train
              </Button>
            </Form>
            {taskId ? (
              <div style={{ marginTop: 12 }}>
                <Space>
                  <Tag color="blue">{stream.status}</Tag>
                  <Paragraph copyable={{ text: taskId }} style={{ margin: 0 }}>
                    {taskId}
                  </Paragraph>
                </Space>
              </div>
            ) : null}
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="Pipeline config (JSON)" size="small">
            <div style={{ height: 380 }}>
              <MonacoEditor
                height="100%"
                defaultLanguage="json"
                value={config}
                onChange={(v) => setConfig(v ?? "")}
                theme="vs-dark"
                options={{ fontSize: 13, minimap: { enabled: false }, scrollBeyondLastLine: false }}
              />
            </div>
          </Card>
          {taskId ? (
            <Card title="Stream" size="small" style={{ marginTop: 16 }}>
              {stream.events.length === 0 ? (
                <Text type="secondary">Waiting for events…</Text>
              ) : (
                <pre
                  style={{
                    fontSize: 11,
                    maxHeight: 280,
                    overflow: "auto",
                    background: "var(--ant-color-bg-elevated)",
                    padding: 8,
                    borderRadius: 6,
                  }}
                >
                  {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n")}
                </pre>
              )}
            </Card>
          ) : null}
        </Col>
      </Row>
    </PageContainer>
  );
}
