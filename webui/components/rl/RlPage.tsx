"use client";

import { RocketOutlined } from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import dynamic from "next/dynamic";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
});

const { Text, Paragraph } = Typography;

interface RLAlgo {
  key: string;
  label: string;
  framework: string;
  policy?: string;
}

interface RLEnv {
  key: string;
  label: string;
  module: string;
  class: string;
  action_space: string;
}

interface RLApplicationParam {
  name: string;
  type: string;
  required?: boolean;
  default?: unknown;
  enum?: unknown[];
  format?: string;
}

interface RLApplication {
  key: string;
  label: string;
  module: string;
  entry: string;
  params: RLApplicationParam[];
}

const DEFAULT_CONFIG = `{
  "agent": "PPO",
  "env": "PortfolioEnv",
  "universe": ["SPY", "AAPL", "MSFT", "GOOGL"],
  "train_start": "2018-01-01",
  "train_end": "2023-06-30",
  "timesteps": 200000,
  "learning_rate": 3e-4,
  "n_envs": 4
}`;

function ParamForm({
  app,
  values,
  onChange,
}: {
  app: RLApplication;
  values: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  return (
    <Form layout="vertical">
      {app.params.map((p) => (
        <Form.Item
          key={p.name}
          label={
            <Space>
              <Text>{p.name}</Text>
              <Tag color="blue">{p.type}</Tag>
              {p.required ? <Tag color="red">required</Tag> : null}
            </Space>
          }
        >
          {p.enum ? (
            <Select
              value={(values[p.name] as string | undefined) ?? (p.default as string)}
              onChange={(v) => onChange({ ...values, [p.name]: v })}
              options={(p.enum as Array<string>).map((v) => ({ value: v, label: v }))}
            />
          ) : p.type === "number" || p.type === "integer" ? (
            <InputNumber
              style={{ width: "100%" }}
              value={(values[p.name] as number | undefined) ?? (p.default as number)}
              onChange={(v) => onChange({ ...values, [p.name]: v })}
              step={p.type === "integer" ? 1 : 0.1}
            />
          ) : p.type === "array" ? (
            <Select
              mode="tags"
              tokenSeparators={[",", " "]}
              value={(values[p.name] as string[]) ?? []}
              onChange={(v) => onChange({ ...values, [p.name]: v })}
            />
          ) : (
            <Input
              value={(values[p.name] as string | undefined) ?? (p.default as string) ?? ""}
              onChange={(e) => onChange({ ...values, [p.name]: e.target.value })}
              placeholder={p.format ?? p.type}
            />
          )}
        </Form.Item>
      ))}
    </Form>
  );
}

export function RlPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  const algos = useApiQuery<{ algos: RLAlgo[] }>({
    queryKey: ["rl", "algos"],
    path: "/rl/algos",
    staleTime: 60_000,
  });
  const envs = useApiQuery<{ envs: RLEnv[] }>({
    queryKey: ["rl", "envs"],
    path: "/rl/envs",
    staleTime: 60_000,
  });
  const apps = useApiQuery<{ applications: RLApplication[] }>({
    queryKey: ["rl", "applications"],
    path: "/rl/applications",
    staleTime: 60_000,
  });

  const [selectedApp, setSelectedApp] = useState<string | null>(null);
  const [appParams, setAppParams] = useState<Record<string, unknown>>({});
  const [appRunName, setAppRunName] = useState<string>("");

  const activeApp = (apps.data?.applications ?? []).find((a) => a.key === selectedApp) || null;

  async function train() {
    const v = await form.validateFields();
    let parsed: unknown;
    try {
      parsed = JSON.parse(config);
    } catch (err) {
      message.error(`Config not valid JSON: ${(err as Error).message}`);
      return;
    }
    try {
      const res = await apiFetch<{ task_id: string }>("/rl/train", {
        method: "POST",
        body: JSON.stringify({ config: parsed, run_name: v.run_name }),
      });
      setTaskId(res.task_id);
      message.success(`RL training queued (${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function runApplication() {
    if (!activeApp) return;
    try {
      const res = await apiFetch<{ task_id: string }>(
        `/rl/applications/${encodeURIComponent(activeApp.key)}/run`,
        {
          method: "POST",
          body: JSON.stringify({ params: appParams, run_name: appRunName || undefined }),
        },
      );
      setTaskId(res.task_id);
      message.success(`Application queued (${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  const trainTab = (
    <Row gutter={16}>
      <Col xs={24} lg={8}>
        <Card title="Train" size="small">
          <Form form={form} layout="vertical" initialValues={{ run_name: "ppo_portfolio" }}>
            <Form.Item label="Run name" name="run_name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Button type="primary" icon={<RocketOutlined />} onClick={train}>
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
        <Card title="Config (JSON)" size="small">
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
      </Col>
    </Row>
  );

  const algosTab = algos.isLoading || !algos.data ? (
    <Skeleton active />
  ) : (
    <Table
      size="small"
      rowKey="key"
      dataSource={algos.data.algos}
      pagination={{ pageSize: 20 }}
      columns={[
        { title: "Key", dataIndex: "key", width: 220 },
        { title: "Label", dataIndex: "label" },
        { title: "Framework", dataIndex: "framework", width: 220 },
        { title: "Policy", dataIndex: "policy" },
      ]}
    />
  );

  const envsTab = envs.isLoading || !envs.data ? (
    <Skeleton active />
  ) : (
    <Table
      size="small"
      rowKey="key"
      dataSource={envs.data.envs}
      pagination={false}
      columns={[
        { title: "Key", dataIndex: "key" },
        { title: "Label", dataIndex: "label" },
        { title: "Class", dataIndex: "class" },
        { title: "Action space", dataIndex: "action_space" },
      ]}
    />
  );

  const applicationsTab = (
    <Row gutter={16}>
      <Col xs={24} lg={8}>
        <Card title="Pick an application" size="small">
          {apps.isLoading || !apps.data ? (
            <Skeleton active />
          ) : (
            <Space direction="vertical" style={{ width: "100%" }}>
              {apps.data.applications.map((a) => (
                <Button
                  key={a.key}
                  block
                  type={selectedApp === a.key ? "primary" : "default"}
                  onClick={() => {
                    setSelectedApp(a.key);
                    setAppParams({});
                  }}
                  style={{ textAlign: "left" }}
                >
                  <Text strong>{a.label}</Text>
                </Button>
              ))}
            </Space>
          )}
        </Card>
      </Col>
      <Col xs={24} lg={16}>
        {!activeApp ? (
          <Card>
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Pick an application." />
          </Card>
        ) : (
          <Card
            size="small"
            title={activeApp.label}
            extra={
              <Space>
                <Input
                  placeholder="run name"
                  value={appRunName}
                  onChange={(e) => setAppRunName(e.target.value)}
                  style={{ width: 200 }}
                />
                <Button type="primary" icon={<RocketOutlined />} onClick={runApplication}>
                  Run
                </Button>
              </Space>
            }
          >
            <ParamForm app={activeApp} values={appParams} onChange={setAppParams} />
          </Card>
        )}
      </Col>
    </Row>
  );

  return (
    <PageContainer
      title="Reinforcement Learning"
      subtitle="Train DRL agents with FinRL-style envs and SB3 wrappers, or run a one-shot application."
    >
      <Tabs
        items={[
          { key: "train", label: "Train", children: trainTab },
          { key: "algos", label: "Algorithms", children: algosTab },
          { key: "envs", label: "Environments", children: envsTab },
          { key: "applications", label: "Applications", children: applicationsTab },
        ]}
      />
      {taskId ? (
        <Card title="Stream" size="small" style={{ marginTop: 16 }}>
          <pre
            style={{
              fontSize: 11,
              maxHeight: 240,
              overflow: "auto",
              background: "var(--ant-color-bg-elevated)",
              padding: 8,
              borderRadius: 6,
            }}
          >
            {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") || "Waiting…"}
          </pre>
          {stream.error ? (
            <Alert type="error" message={stream.error} style={{ marginTop: 8 }} />
          ) : null}
        </Card>
      ) : null}
    </PageContainer>
  );
}
