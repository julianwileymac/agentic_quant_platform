"use client";

import { ArrowLeftOutlined, RocketOutlined } from "@ant-design/icons";
import { App, Alert, Button, Card, Col, Form, Input, Row, Select, Skeleton, Space, Typography } from "antd";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { normaliseBacktestConfigShape } from "@/components/backtest/backtestLabConfig";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
  loading: () => <Skeleton active />,
});

const { Text, Paragraph } = Typography;

const DEFAULT_CONFIG = `# Backend-compatible shape: strategy + backtest blocks.
{
  "strategy": {
    "class": "FrameworkAlgorithm",
    "module_path": "aqp.strategies.framework",
    "kwargs": {
      "universe_model": {
        "class": "StaticUniverse",
        "module_path": "aqp.strategies.universes",
        "kwargs": { "symbols": ["SPY", "AAPL", "MSFT"] }
      },
      "alpha_model": {
        "class": "MomentumAlpha",
        "module_path": "aqp.strategies.momentum",
        "kwargs": {
          "lookback": 90,
          "top_quantile": 0.3,
          "bottom_quantile": 0.3,
          "allow_short": false
        }
      },
      "portfolio_model": {
        "class": "EqualWeightPortfolio",
        "module_path": "aqp.strategies.portfolio",
        "kwargs": { "max_positions": 5 }
      },
      "risk_model": {
        "class": "BasicRiskModel",
        "module_path": "aqp.strategies.risk_models",
        "kwargs": { "max_position_pct": 0.25, "max_drawdown_pct": 0.2 }
      },
      "execution_model": {
        "class": "MarketOrderExecution",
        "module_path": "aqp.strategies.execution",
        "kwargs": {}
      }
    }
  },
  "backtest": {
    "engine": "event",
    "kwargs": {
      "initial_cash": 100000,
      "commission_pct": 0.0005,
      "slippage_bps": 2,
      "start": "2022-01-01",
      "end": "2024-12-31"
    }
  }
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
    const normalized = normaliseBacktestConfigShape(parsed, values.engine ?? "event");
    if (!normalized) {
      message.error("Config must include both `strategy` and `backtest` objects.");
      return;
    }
    try {
      const res = await apiFetch<SubmitResp>("/backtest/run", {
        method: "POST",
        body: JSON.stringify({ config: normalized, run_name: values.run_name || "ad_hoc" }),
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
            <Form form={form} layout="vertical" initialValues={{ run_name: "ad_hoc", engine: "event" }}>
              <Form.Item
                label="Run name"
                name="run_name"
                rules={[{ required: true, message: "Required" }]}
              >
                <Input />
              </Form.Item>
              <Form.Item label="Engine" name="engine">
                <Select
                  defaultValue="event"
                  options={[
                    { value: "event", label: "Event Driven" },
                    { value: "vectorbt-pro", label: "Vectorbt Pro" },
                    { value: "vectorbt", label: "Vectorbt" },
                    { value: "backtesting", label: "backtesting.py" },
                    { value: "fallback", label: "Fallback cascade" },
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
