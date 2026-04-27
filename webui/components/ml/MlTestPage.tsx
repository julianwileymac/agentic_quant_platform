"use client";

import { ExperimentOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";
import { useLiveStream } from "@/lib/ws/useLiveStream";

const { Text } = Typography;

interface ModelRow {
  id: string;
  registry_name?: string | null;
  algo?: string | null;
  stage?: string | null;
  mlflow_run_id?: string | null;
  created_at?: string;
}

interface SplitPlanSummary {
  id: string;
  name: string;
  method: string;
}

interface DeploymentRow {
  id: string;
  name: string;
  status: string;
  alpha_class?: string;
}

interface EvaluationResp {
  task_id: string;
  mlflow_run_id?: string | null;
  metrics?: Record<string, number>;
  status?: string;
  registry_name?: string;
}

interface UniverseResponse {
  items?: { ticker?: string; vt_symbol?: string }[];
}

interface LiveTestResponse {
  channel_id: string;
  ws_url: string;
}

export function MlTestPage() {
  const { message } = App.useApp();

  // ---------- Historical state ----------
  const [registryName, setRegistryName] = useState<string>("");
  const [splitPlanId, setSplitPlanId] = useState<string>("");
  const [adhocSymbols, setAdhocSymbols] = useState<string[]>(["AAPL", "MSFT"]);
  const [adhocStart, setAdhocStart] = useState("2023-01-01");
  const [adhocEnd, setAdhocEnd] = useState("2024-06-30");
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  const evaluation = useApiQuery<EvaluationResp>({
    queryKey: ["ml", "evaluation", taskId ?? ""],
    path: `/ml/evaluations/${taskId ?? ""}`,
    enabled: Boolean(taskId) && stream.status === "closed",
  });

  // ---------- Live state ----------
  const [deploymentId, setDeploymentId] = useState<string>("");
  const [liveSymbols, setLiveSymbols] = useState<string[]>(["AAPL", "MSFT"]);
  const [liveChannel, setLiveChannel] = useState<string | null>(null);
  const [streamingOn, setStreamingOn] = useState(false);

  const models = useApiQuery<ModelRow[]>({
    queryKey: ["ml", "models"],
    path: "/ml/models",
    select: (raw) => (Array.isArray(raw) ? (raw as ModelRow[]) : []),
  });

  const splitPlans = useApiQuery<SplitPlanSummary[]>({
    queryKey: ["ml", "split-plans"],
    path: "/ml/split-plans",
  });

  const deployments = useApiQuery<DeploymentRow[]>({
    queryKey: ["ml", "deployments"],
    path: "/ml/deployments",
    select: (raw) => (Array.isArray(raw) ? (raw as DeploymentRow[]) : []),
  });

  const universe = useApiQuery<UniverseResponse>({
    queryKey: ["data", "universe", "ml-test"],
    path: "/data/universe",
    query: { limit: 500 },
    staleTime: 60_000,
  });
  const universeOptions = (universe.data?.items ?? []).map((it) => {
    const vt = it.vt_symbol ?? `${it.ticker ?? ""}.NASDAQ`;
    return { value: vt, label: vt };
  });

  const live = useLiveStream({ channelId: streamingOn ? liveChannel : null, bufferSize: 256 });

  useEffect(() => {
    return () => {
      if (liveChannel) {
        apiFetch(`/ml/live-test/${liveChannel}`, { method: "DELETE" }).catch(() => {
          /* noop */
        });
      }
    };
  }, [liveChannel]);

  async function startEvaluate() {
    if (!registryName) {
      message.warning("Pick a model first");
      return;
    }
    const body: Record<string, unknown> = { registry_name: registryName };
    if (splitPlanId) {
      body.dataset_cfg = { split_plan_id: splitPlanId };
    } else {
      body.dataset_cfg = {
        class: "DatasetH",
        module_path: "aqp.ml.dataset",
        kwargs: {
          handler: {
            class: "Alpha158",
            module_path: "aqp.ml.features.alpha158",
            kwargs: {
              instruments: adhocSymbols,
              start_time: adhocStart,
              end_time: adhocEnd,
            },
          },
          segments: { test: [adhocStart, adhocEnd] },
        },
      };
    }
    try {
      const res = await apiFetch<{ task_id: string }>("/ml/evaluate", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setTaskId(res.task_id);
      message.success(`Evaluation queued (${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function startLive() {
    if (!deploymentId) {
      message.warning("Pick a deployment first");
      return;
    }
    try {
      const res = await apiFetch<LiveTestResponse>("/ml/live-test/start", {
        method: "POST",
        body: JSON.stringify({
          deployment_id: deploymentId,
          venue: "simulated",
          symbols: liveSymbols,
        }),
      });
      setLiveChannel(res.channel_id);
      setStreamingOn(true);
      message.success(`Live test channel ${res.channel_id} opened`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function stopLive() {
    if (!liveChannel) return;
    try {
      await apiFetch(`/ml/live-test/${liveChannel}`, { method: "DELETE" });
      message.success("Live test stopped");
    } catch (err) {
      message.error((err as Error).message);
    }
    setStreamingOn(false);
    setLiveChannel(null);
  }

  const metricItems = Object.entries(evaluation.data?.metrics ?? {});

  // Build a small bar→prediction overlay timeline from the live buffer.
  const liveTimeline = live.buffer
    .filter((ev) => ev.kind === "bar" || ev.kind === "signal")
    .slice(-120)
    .map((ev, idx) => ({
      idx,
      t: ev.timestamp,
      close: ev.kind === "bar" ? Number(ev.close) : null,
      strength: ev.kind === "signal" ? Number(ev.strength) : null,
    }));

  return (
    <PageContainer
      title="ML Test"
      subtitle="Validate models against historical splits or stream predictions on live data."
    >
      <Tabs
        items={[
          {
            key: "historical",
            label: "Historical",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={10}>
                  <Card title="Evaluate" size="small">
                    <Form layout="vertical">
                      <Form.Item label="Model">
                        <Select
                          value={registryName}
                          onChange={setRegistryName}
                          placeholder="Pick a registered model"
                          options={(models.data ?? []).map((m) => ({
                            value: m.registry_name ?? m.id,
                            label: `${m.registry_name ?? m.id} ${m.algo ? `· ${m.algo}` : ""}`,
                          }))}
                        />
                      </Form.Item>
                      <Form.Item label="Split plan (optional)">
                        <Select
                          value={splitPlanId}
                          onChange={setSplitPlanId}
                          allowClear
                          placeholder="Use a saved split plan"
                          options={(splitPlans.data ?? []).map((s) => ({
                            value: s.id,
                            label: `${s.name} (${s.method})`,
                          }))}
                        />
                      </Form.Item>
                      {!splitPlanId ? (
                        <>
                          <Form.Item label="Symbols">
                            <Select
                              mode="multiple"
                              value={adhocSymbols}
                              onChange={setAdhocSymbols}
                              options={
                                universeOptions.length
                                  ? universeOptions
                                  : adhocSymbols.map((s) => ({ value: s, label: s }))
                              }
                              maxTagCount={4}
                            />
                          </Form.Item>
                          <Row gutter={12}>
                            <Col xs={12}>
                              <Form.Item label="Start">
                                <Input value={adhocStart} onChange={(e) => setAdhocStart(e.target.value)} />
                              </Form.Item>
                            </Col>
                            <Col xs={12}>
                              <Form.Item label="End">
                                <Input value={adhocEnd} onChange={(e) => setAdhocEnd(e.target.value)} />
                              </Form.Item>
                            </Col>
                          </Row>
                        </>
                      ) : null}
                      <Button
                        type="primary"
                        icon={<ExperimentOutlined />}
                        onClick={startEvaluate}
                        disabled={!registryName}
                      >
                        Run evaluate
                      </Button>
                    </Form>
                  </Card>
                </Col>
                <Col xs={24} lg={14}>
                  <Card title="Run output" size="small">
                    {!taskId ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Run an evaluation to see results" />
                    ) : (
                      <>
                        <Space style={{ marginBottom: 8 }}>
                          <Tag>task: {taskId}</Tag>
                          <Tag color={stream.status === "closed" ? "green" : "blue"}>
                            stream: {stream.status}
                          </Tag>
                        </Space>
                        {evaluation.isLoading ? <Spin size="small" /> : null}
                        {evaluation.error ? (
                          <Alert
                            type="warning"
                            showIcon
                            message="Could not fetch evaluation result yet"
                            description={evaluation.error.message}
                          />
                        ) : null}
                        {metricItems.length > 0 ? (
                          <Descriptions column={2} size="small" bordered style={{ marginTop: 8 }}>
                            {metricItems.map(([k, v]) => (
                              <Descriptions.Item key={k} label={k}>
                                {typeof v === "number" ? v.toFixed(4) : String(v)}
                              </Descriptions.Item>
                            ))}
                          </Descriptions>
                        ) : null}
                        <pre
                          style={{
                            marginTop: 8,
                            fontSize: 11,
                            maxHeight: 240,
                            overflow: "auto",
                            background: "var(--ant-color-bg-elevated)",
                            padding: 8,
                            borderRadius: 6,
                          }}
                        >
                          {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") || "—"}
                        </pre>
                      </>
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: "live",
            label: "Live",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={10}>
                  <Card title="Live model inference" size="small">
                    <Form layout="vertical">
                      <Form.Item label="Deployment">
                        <Select
                          value={deploymentId}
                          onChange={setDeploymentId}
                          placeholder="Pick an active deployment"
                          options={(deployments.data ?? []).map((d) => ({
                            value: d.id,
                            label: `${d.name} (${d.status})`,
                          }))}
                        />
                      </Form.Item>
                      <Form.Item label="Symbols">
                        <Select
                          mode="multiple"
                          value={liveSymbols}
                          onChange={setLiveSymbols}
                          options={
                            universeOptions.length
                              ? universeOptions
                              : liveSymbols.map((s) => ({ value: s, label: s }))
                          }
                          maxTagCount={4}
                        />
                      </Form.Item>
                      <Space>
                        <Button
                          type="primary"
                          icon={<ThunderboltOutlined />}
                          onClick={liveChannel ? stopLive : startLive}
                          disabled={!deploymentId}
                        >
                          {liveChannel ? "Stop" : "Start streaming"}
                        </Button>
                        <Switch
                          checked={streamingOn}
                          onChange={setStreamingOn}
                          checkedChildren="streaming"
                          unCheckedChildren="paused"
                          disabled={!liveChannel}
                        />
                      </Space>
                    </Form>
                  </Card>
                </Col>
                <Col xs={24} lg={14}>
                  <Card title="Streaming predictions" size="small">
                    {!liveChannel ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Start the bridge to subscribe" />
                    ) : (
                      <>
                        <Space style={{ marginBottom: 8 }}>
                          <Tag color="purple">channel {liveChannel}</Tag>
                          <Tag color="blue">{live.status}</Tag>
                          {live.error ? <Tag color="red">{live.error}</Tag> : null}
                        </Space>
                        <ResponsiveContainer width="100%" height={220}>
                          <LineChart data={liveTimeline} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                            <XAxis dataKey="idx" hide />
                            <YAxis fontSize={11} width={48} />
                            <Tooltip contentStyle={{ fontSize: 11 }} />
                            <Line
                              type="monotone"
                              dataKey="close"
                              stroke="#3b82f6"
                              dot={false}
                              strokeWidth={1.5}
                              isAnimationActive={false}
                            />
                            <Line
                              type="monotone"
                              dataKey="strength"
                              stroke="#10b981"
                              dot={false}
                              strokeWidth={1.5}
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                        <List
                          size="small"
                          style={{ marginTop: 8 }}
                          dataSource={live.buffer.slice(-10).reverse()}
                          renderItem={(ev) => (
                            <List.Item style={{ padding: "4px 0" }}>
                              <Space size={6}>
                                <Tag>{ev.kind}</Tag>
                                <Text strong style={{ fontSize: 12 }}>
                                  {ev.vt_symbol ?? "—"}
                                </Text>
                                <Text type="secondary" style={{ fontSize: 11 }}>
                                  {ev.timestamp}
                                </Text>
                              </Space>
                            </List.Item>
                          )}
                        />
                      </>
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: "models",
            label: "Models",
            children: (
              <Card size="small">
                <Table
                  size="small"
                  rowKey="id"
                  dataSource={models.data ?? []}
                  pagination={{ pageSize: 15 }}
                  columns={[
                    { title: "Registry name", dataIndex: "registry_name" },
                    { title: "Algo", dataIndex: "algo" },
                    { title: "Stage", dataIndex: "stage" },
                    { title: "Created", dataIndex: "created_at" },
                  ]}
                />
              </Card>
            ),
          },
        ]}
      />
    </PageContainer>
  );
}
