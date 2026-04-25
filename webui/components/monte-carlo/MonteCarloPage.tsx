"use client";

import { App, Button, Card, Col, Form, Input, InputNumber, Row, Select, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { FanChart, type FanPoint } from "@/components/charts";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws";

const { Text, Paragraph } = Typography;

export function MonteCarloPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);
  const [series, setSeries] = useState<FanPoint[]>([]);

  async function submit() {
    const v = await form.validateFields();
    try {
      const res = await apiFetch<{ task_id: string }>("/backtest/monte_carlo", {
        method: "POST",
        body: JSON.stringify({
          backtest_id: v.backtest_id,
          n_runs: Number(v.n_runs),
          method: v.method,
        }),
      });
      setTaskId(res.task_id);
      setSeries([]);
      message.success(`Monte Carlo queued (${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  // Pull fan-chart points out of the stream as the worker emits them.
  // We accept any shape `{ data: { fan: [...] } }` published by the task.
  if (stream.events.length > 0 && series.length === 0) {
    for (let i = stream.events.length - 1; i >= 0; i -= 1) {
      const evt = stream.events[i];
      const fan = (evt?.data as { fan?: FanPoint[] } | undefined)?.fan;
      if (Array.isArray(fan) && fan.length > 0) {
        setSeries(fan);
        break;
      }
    }
  }

  return (
    <PageContainer
      title="Monte Carlo"
      subtitle="Resample backtest returns to estimate the distribution of outcomes."
    >
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="Submit" size="small">
            <Form
              form={form}
              layout="vertical"
              initialValues={{ n_runs: 200, method: "bootstrap" }}
            >
              <Form.Item
                label="Backtest ID"
                name="backtest_id"
                rules={[{ required: true, message: "Required" }]}
              >
                <Input placeholder="A completed backtest run id" />
              </Form.Item>
              <Form.Item label="Method" name="method">
                <Select
                  options={[
                    { value: "bootstrap", label: "Bootstrap returns" },
                    { value: "shuffle", label: "Shuffle returns" },
                    { value: "parametric", label: "Parametric (normal)" },
                  ]}
                />
              </Form.Item>
              <Form.Item label="Number of runs" name="n_runs">
                <InputNumber style={{ width: "100%" }} min={50} max={5000} step={50} />
              </Form.Item>
              <Button type="primary" onClick={submit}>
                Run
              </Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="Distribution" size="small">
            {series.length > 0 ? (
              <FanChart data={series} height={360} />
            ) : (
              <Text type="secondary">
                Submit a Monte Carlo run; the fan chart populates as the worker streams partial results.
              </Text>
            )}
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
      </Row>
    </PageContainer>
  );
}
