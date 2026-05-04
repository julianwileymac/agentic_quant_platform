"use client";

import {
  CompressOutlined,
  ExperimentOutlined,
  RadarChartOutlined,
  ThunderboltOutlined,
  UploadOutlined,
} from "@ant-design/icons";
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
  Upload,
  type UploadProps,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";
import { useLiveStream } from "@/lib/ws/useLiveStream";

const { Text, Paragraph } = Typography;

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

  // ---------- Single / Batch / Compare / Scenario state ----------
  const [singleDeploymentId, setSingleDeploymentId] = useState<string>("");
  const [singleFeatureRowText, setSingleFeatureRowText] = useState<string>(
    '{"feature_a": 0.5, "feature_b": -0.2}',
  );
  const [singlePrediction, setSinglePrediction] = useState<number | null>(null);
  const [singleLoading, setSingleLoading] = useState(false);

  const [batchDeploymentId, setBatchDeploymentId] = useState<string>("");
  const [batchSymbols, setBatchSymbols] = useState<string[]>(["AAPL", "MSFT"]);
  const [batchStart, setBatchStart] = useState("2024-01-01");
  const [batchEnd, setBatchEnd] = useState("2024-06-30");
  const [batchTaskId, setBatchTaskId] = useState<string | null>(null);
  const batchStream = useChatStream(batchTaskId);

  const [compareA, setCompareA] = useState<string>("");
  const [compareB, setCompareB] = useState<string>("");
  const [compareSymbols, setCompareSymbols] = useState<string[]>(["AAPL"]);
  const [compareStart, setCompareStart] = useState("2024-01-01");
  const [compareEnd, setCompareEnd] = useState("2024-06-30");
  const [compareTaskId, setCompareTaskId] = useState<string | null>(null);
  const compareStream = useChatStream(compareTaskId);

  const [scenarioDeploymentId, setScenarioDeploymentId] = useState<string>("");
  const [scenarioFeatureRowText, setScenarioFeatureRowText] = useState<string>(
    '{"feature_a": 0.5, "feature_b": -0.2}',
  );
  const [scenarioPerturbations, setScenarioPerturbations] = useState<number[]>([
    -0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2,
  ]);
  const [scenarioRows, setScenarioRows] = useState<
    { feature: string; perturbation: number; prediction: number; delta: number }[]
  >([]);
  const [scenarioBaseline, setScenarioBaseline] = useState<number | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);

  const [csvDeploymentId, setCsvDeploymentId] = useState<string>("");
  const [csvResult, setCsvResult] = useState<{
    n_rows: number;
    predictions_summary: { mean: number; std: number; min: number; max: number };
    rows: Array<Record<string, unknown>>;
  } | null>(null);

  useEffect(() => {
    return () => {
      if (liveChannel) {
        apiFetch(`/ml/live-test/${liveChannel}`, { method: "DELETE" }).catch(() => {
          /* noop */
        });
      }
    };
  }, [liveChannel]);

  function _parseRow(text: string): Record<string, number> {
    try {
      const obj = JSON.parse(text) as Record<string, unknown>;
      const out: Record<string, number> = {};
      for (const [k, v] of Object.entries(obj)) {
        const n = typeof v === "number" ? v : parseFloat(String(v));
        if (Number.isFinite(n)) out[k] = n;
      }
      return out;
    } catch {
      throw new Error("feature_row must be valid JSON");
    }
  }

  async function runSinglePredict() {
    if (!singleDeploymentId) {
      message.warning("Pick a deployment first");
      return;
    }
    setSingleLoading(true);
    setSinglePrediction(null);
    try {
      const row = _parseRow(singleFeatureRowText);
      const res = await apiFetch<{ prediction: number }>("/ml/test/single", {
        method: "POST",
        body: JSON.stringify({
          deployment_id: singleDeploymentId,
          feature_row: row,
          sync: true,
        }),
      });
      setSinglePrediction(res.prediction);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSingleLoading(false);
    }
  }

  async function runBatchPredict() {
    if (!batchDeploymentId) {
      message.warning("Pick a deployment first");
      return;
    }
    try {
      const res = await apiFetch<{ task_id: string }>("/ml/test/batch", {
        method: "POST",
        body: JSON.stringify({
          deployment_id: batchDeploymentId,
          symbols: batchSymbols,
          start: batchStart,
          end: batchEnd,
          last_n: 200,
        }),
      });
      setBatchTaskId(res.task_id);
      message.success(`Batch queued (${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function runCompare() {
    if (!compareA || !compareB) {
      message.warning("Pick both deployments");
      return;
    }
    if (compareA === compareB) {
      message.warning("Pick two different deployments");
      return;
    }
    try {
      const res = await apiFetch<{ task_id: string }>("/ml/test/compare", {
        method: "POST",
        body: JSON.stringify({
          deployment_id_a: compareA,
          deployment_id_b: compareB,
          symbols: compareSymbols,
          start: compareStart,
          end: compareEnd,
          last_n: 200,
        }),
      });
      setCompareTaskId(res.task_id);
      message.success(`Comparison queued (${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function runScenario() {
    if (!scenarioDeploymentId) {
      message.warning("Pick a deployment first");
      return;
    }
    setScenarioLoading(true);
    setScenarioRows([]);
    setScenarioBaseline(null);
    try {
      const row = _parseRow(scenarioFeatureRowText);
      const res = await apiFetch<{
        baseline_prediction: number;
        rows: { feature: string; perturbation: number; prediction: number; delta: number }[];
      }>("/ml/test/scenario", {
        method: "POST",
        body: JSON.stringify({
          deployment_id: scenarioDeploymentId,
          feature_row: row,
          perturbations: scenarioPerturbations,
          sync: true,
        }),
      });
      setScenarioBaseline(res.baseline_prediction);
      setScenarioRows(res.rows ?? []);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setScenarioLoading(false);
    }
  }

  const csvUploadProps: UploadProps = {
    maxCount: 1,
    accept: ".csv,text/csv",
    beforeUpload: async (file) => {
      if (!csvDeploymentId) {
        message.warning("Pick a deployment first");
        return Upload.LIST_IGNORE;
      }
      const form = new FormData();
      form.append("file", file);
      try {
        const res = await fetch(`/api/ml/test/upload-csv?deployment_id=${encodeURIComponent(csvDeploymentId)}`, {
          method: "POST",
          body: form,
        });
        if (!res.ok) throw new Error(await res.text());
        const json = (await res.json()) as typeof csvResult;
        setCsvResult(json);
        message.success(`Scored ${json?.n_rows ?? 0} rows`);
      } catch (err) {
        message.error((err as Error).message);
      }
      return Upload.LIST_IGNORE;
    },
  };

  const scenarioBars = useMemo(() => {
    return scenarioRows.map((r, i) => ({
      idx: i,
      label: `${r.feature} ${(r.perturbation * 100).toFixed(0)}%`,
      delta: r.delta,
    }));
  }, [scenarioRows]);

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
            key: "single",
            label: "Single Predict",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={10}>
                  <Card title="Single-row inference" size="small">
                    <Form layout="vertical">
                      <Form.Item label="Deployment">
                        <Select
                          value={singleDeploymentId}
                          onChange={setSingleDeploymentId}
                          placeholder="Pick an active deployment"
                          options={(deployments.data ?? []).map((d) => ({
                            value: d.id,
                            label: `${d.name} (${d.status})`,
                          }))}
                        />
                      </Form.Item>
                      <Form.Item
                        label="Feature row (JSON)"
                        help="Map of column name to numeric value. Schema is model-specific."
                      >
                        <Input.TextArea
                          rows={6}
                          value={singleFeatureRowText}
                          onChange={(e) => setSingleFeatureRowText(e.target.value)}
                          style={{ fontFamily: "monospace" }}
                        />
                      </Form.Item>
                      <Button
                        type="primary"
                        loading={singleLoading}
                        onClick={runSinglePredict}
                        disabled={!singleDeploymentId}
                      >
                        Predict
                      </Button>
                    </Form>
                  </Card>
                </Col>
                <Col xs={24} lg={14}>
                  <Card title="Prediction" size="small">
                    {singlePrediction === null ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Submit a row to score" />
                    ) : (
                      <Descriptions column={1} bordered size="small">
                        <Descriptions.Item label="Score">
                          <Text strong>{singlePrediction.toFixed(6)}</Text>
                        </Descriptions.Item>
                        <Descriptions.Item label="Sign">
                          <Tag color={singlePrediction >= 0 ? "green" : "red"}>
                            {singlePrediction >= 0 ? "long bias" : "short bias"}
                          </Tag>
                        </Descriptions.Item>
                      </Descriptions>
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: "batch",
            label: "Batch",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={10}>
                  <Card title="Batch inference" size="small">
                    <Form layout="vertical">
                      <Form.Item label="Deployment">
                        <Select
                          value={batchDeploymentId}
                          onChange={setBatchDeploymentId}
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
                          value={batchSymbols}
                          onChange={setBatchSymbols}
                          options={
                            universeOptions.length
                              ? universeOptions
                              : batchSymbols.map((s) => ({ value: s, label: s }))
                          }
                          maxTagCount={4}
                        />
                      </Form.Item>
                      <Row gutter={12}>
                        <Col xs={12}>
                          <Form.Item label="Start">
                            <Input value={batchStart} onChange={(e) => setBatchStart(e.target.value)} />
                          </Form.Item>
                        </Col>
                        <Col xs={12}>
                          <Form.Item label="End">
                            <Input value={batchEnd} onChange={(e) => setBatchEnd(e.target.value)} />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Button type="primary" onClick={runBatchPredict} disabled={!batchDeploymentId}>
                        Run batch
                      </Button>
                    </Form>
                  </Card>

                  <Card title="Or upload a CSV" size="small" style={{ marginTop: 12 }}>
                    <Form layout="vertical">
                      <Form.Item label="Deployment">
                        <Select
                          value={csvDeploymentId}
                          onChange={setCsvDeploymentId}
                          placeholder="Pick an active deployment"
                          options={(deployments.data ?? []).map((d) => ({
                            value: d.id,
                            label: `${d.name} (${d.status})`,
                          }))}
                        />
                      </Form.Item>
                      <Upload {...csvUploadProps}>
                        <Button icon={<UploadOutlined />} disabled={!csvDeploymentId}>
                          Upload CSV
                        </Button>
                      </Upload>
                    </Form>
                  </Card>
                </Col>
                <Col xs={24} lg={14}>
                  <Card title="Output" size="small">
                    {batchTaskId ? (
                      <>
                        <Space style={{ marginBottom: 8 }}>
                          <Tag>task: {batchTaskId}</Tag>
                          <Tag color={batchStream.status === "closed" ? "green" : "blue"}>
                            stream: {batchStream.status}
                          </Tag>
                        </Space>
                        <pre
                          style={{
                            fontSize: 11,
                            maxHeight: 200,
                            overflow: "auto",
                            background: "var(--ant-color-bg-elevated)",
                            padding: 8,
                            borderRadius: 6,
                          }}
                        >
                          {batchStream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") ||
                            "—"}
                        </pre>
                      </>
                    ) : null}
                    {csvResult ? (
                      <>
                        <Descriptions column={2} bordered size="small" style={{ marginTop: 8 }}>
                          <Descriptions.Item label="rows">{csvResult.n_rows}</Descriptions.Item>
                          <Descriptions.Item label="mean">
                            {csvResult.predictions_summary.mean.toFixed(4)}
                          </Descriptions.Item>
                          <Descriptions.Item label="std">
                            {csvResult.predictions_summary.std.toFixed(4)}
                          </Descriptions.Item>
                          <Descriptions.Item label="min">
                            {csvResult.predictions_summary.min.toFixed(4)}
                          </Descriptions.Item>
                          <Descriptions.Item label="max">
                            {csvResult.predictions_summary.max.toFixed(4)}
                          </Descriptions.Item>
                        </Descriptions>
                      </>
                    ) : null}
                    {!batchTaskId && !csvResult ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Run a batch to see results" />
                    ) : null}
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: "compare",
            label: "A/B Compare",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={10}>
                  <Card title="A/B compare" size="small">
                    <Form layout="vertical">
                      <Form.Item label="Deployment A">
                        <Select
                          value={compareA}
                          onChange={setCompareA}
                          options={(deployments.data ?? []).map((d) => ({
                            value: d.id,
                            label: `${d.name} (${d.status})`,
                          }))}
                        />
                      </Form.Item>
                      <Form.Item label="Deployment B">
                        <Select
                          value={compareB}
                          onChange={setCompareB}
                          options={(deployments.data ?? []).map((d) => ({
                            value: d.id,
                            label: `${d.name} (${d.status})`,
                          }))}
                        />
                      </Form.Item>
                      <Form.Item label="Symbols">
                        <Select
                          mode="multiple"
                          value={compareSymbols}
                          onChange={setCompareSymbols}
                          options={
                            universeOptions.length
                              ? universeOptions
                              : compareSymbols.map((s) => ({ value: s, label: s }))
                          }
                          maxTagCount={4}
                        />
                      </Form.Item>
                      <Row gutter={12}>
                        <Col xs={12}>
                          <Form.Item label="Start">
                            <Input value={compareStart} onChange={(e) => setCompareStart(e.target.value)} />
                          </Form.Item>
                        </Col>
                        <Col xs={12}>
                          <Form.Item label="End">
                            <Input value={compareEnd} onChange={(e) => setCompareEnd(e.target.value)} />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Button
                        type="primary"
                        icon={<CompressOutlined />}
                        onClick={runCompare}
                        disabled={!compareA || !compareB}
                      >
                        Compare
                      </Button>
                    </Form>
                  </Card>
                </Col>
                <Col xs={24} lg={14}>
                  <Card title="Output" size="small">
                    {!compareTaskId ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Submit a comparison to see results" />
                    ) : (
                      <>
                        <Space style={{ marginBottom: 8 }}>
                          <Tag>task: {compareTaskId}</Tag>
                          <Tag color={compareStream.status === "closed" ? "green" : "blue"}>
                            stream: {compareStream.status}
                          </Tag>
                        </Space>
                        <pre
                          style={{
                            fontSize: 11,
                            maxHeight: 320,
                            overflow: "auto",
                            background: "var(--ant-color-bg-elevated)",
                            padding: 8,
                            borderRadius: 6,
                          }}
                        >
                          {compareStream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") ||
                            "—"}
                        </pre>
                      </>
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: "scenario",
            label: "Scenario / What-if",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={10}>
                  <Card title="Sensitivity sweep" size="small">
                    <Form layout="vertical">
                      <Form.Item label="Deployment">
                        <Select
                          value={scenarioDeploymentId}
                          onChange={setScenarioDeploymentId}
                          options={(deployments.data ?? []).map((d) => ({
                            value: d.id,
                            label: `${d.name} (${d.status})`,
                          }))}
                        />
                      </Form.Item>
                      <Form.Item label="Baseline feature row (JSON)">
                        <Input.TextArea
                          rows={6}
                          value={scenarioFeatureRowText}
                          onChange={(e) => setScenarioFeatureRowText(e.target.value)}
                          style={{ fontFamily: "monospace" }}
                        />
                      </Form.Item>
                      <Form.Item label="Perturbations (% as decimal)">
                        <Select
                          mode="tags"
                          value={scenarioPerturbations.map(String)}
                          onChange={(vals) =>
                            setScenarioPerturbations(
                              vals.map((v) => parseFloat(v)).filter((n) => Number.isFinite(n)),
                            )
                          }
                        />
                      </Form.Item>
                      <Button
                        type="primary"
                        icon={<RadarChartOutlined />}
                        loading={scenarioLoading}
                        onClick={runScenario}
                        disabled={!scenarioDeploymentId}
                      >
                        Sweep
                      </Button>
                    </Form>
                  </Card>
                </Col>
                <Col xs={24} lg={14}>
                  <Card title="Sensitivity table" size="small">
                    {scenarioRows.length === 0 ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Run a sweep to see results" />
                    ) : (
                      <>
                        {scenarioBaseline !== null ? (
                          <Paragraph style={{ marginBottom: 8 }}>
                            Baseline prediction:{" "}
                            <Text strong>{scenarioBaseline.toFixed(6)}</Text>
                          </Paragraph>
                        ) : null}
                        <ResponsiveContainer width="100%" height={240}>
                          <BarChart data={scenarioBars} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="idx" hide />
                            <YAxis fontSize={11} width={48} />
                            <Tooltip
                              formatter={(value, _name, item) => [
                                Number(value).toFixed(4),
                                item?.payload?.label ?? "delta",
                              ]}
                            />
                            <Bar dataKey="delta">
                              {scenarioBars.map((row) => (
                                <Cell
                                  key={row.idx}
                                  fill={row.delta >= 0 ? "#10b981" : "#ef4444"}
                                />
                              ))}
                            </Bar>
                            <Legend />
                          </BarChart>
                        </ResponsiveContainer>
                        <Table
                          size="small"
                          rowKey={(row) => `${row.feature}:${row.perturbation}`}
                          dataSource={scenarioRows}
                          pagination={{ pageSize: 10 }}
                          columns={[
                            { title: "Feature", dataIndex: "feature" },
                            {
                              title: "Perturbation",
                              dataIndex: "perturbation",
                              render: (v: number) => `${(v * 100).toFixed(1)}%`,
                            },
                            {
                              title: "Prediction",
                              dataIndex: "prediction",
                              render: (v: number) => v.toFixed(4),
                            },
                            {
                              title: "Delta",
                              dataIndex: "delta",
                              render: (v: number) => (
                                <Text type={v >= 0 ? "success" : "danger"}>{v.toFixed(4)}</Text>
                              ),
                            },
                          ]}
                        />
                      </>
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
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
