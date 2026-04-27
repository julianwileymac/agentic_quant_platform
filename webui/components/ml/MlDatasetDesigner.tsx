"use client";

import {
  DeleteOutlined,
  PlusOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface ProcessorMeta {
  name: string;
  kind: "null" | "filter" | "normalize" | "categorical" | "outlier";
  description: string;
  params: { name: string; default: unknown; type: string; description?: string }[];
}

interface SplitArtifact {
  fold_name: string;
  segment: string;
  start_time?: string | null;
  end_time?: string | null;
  n_indices: number;
}

interface SplitPlanSummary {
  id: string;
  name: string;
  method: string;
  description?: string;
  segments: Record<string, unknown>;
  config: Record<string, unknown>;
  created_at: string;
  artifacts: SplitArtifact[];
}

interface PipelineRecipeSummary {
  id: string;
  name: string;
  version: number;
  description?: string;
  shared_processors: { class: string; kwargs?: Record<string, unknown> }[];
  infer_processors: { class: string; kwargs?: Record<string, unknown> }[];
  learn_processors: { class: string; kwargs?: Record<string, unknown> }[];
  created_at: string;
}

interface IndicatorEntry {
  id: string;
  name: string;
  group: string;
  description: string;
  outputs: string[];
}

interface CatalogResponse {
  groups: { name: string; indicators: IndicatorEntry[] }[];
}

interface FeatureCandidate {
  id: string;
  source: string;
  domain: string;
  field: string;
  description: string;
}

interface FeatureCandidatesResponse {
  candidates: FeatureCandidate[];
}

interface UniverseEntry {
  ticker?: string;
  vt_symbol?: string;
}

interface UniverseResponse {
  items?: UniverseEntry[];
}

const PROCESSOR_MODULE: Record<string, string> = {
  Fillna: "aqp.ml.processors",
  DropnaLabel: "aqp.ml.processors",
  FilterCol: "aqp.ml.processors",
  CSZScoreNorm: "aqp.ml.processors",
  CSRankNorm: "aqp.ml.processors",
  MinMaxNorm: "aqp.ml.processors",
  RobustScaler: "aqp.ml.processors",
  OneHotEncode: "aqp.ml.processors",
  OrdinalEncode: "aqp.ml.processors",
  TargetEncode: "aqp.ml.processors",
  HashEncode: "aqp.ml.processors",
  FrequencyEncode: "aqp.ml.processors",
  PyODOutlierFilter: "aqp.ml.processors",
};

function defaultKwargs(meta: ProcessorMeta): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of meta.params) {
    if (p.default !== undefined) out[p.name] = p.default;
  }
  return out;
}

function processorSpec(meta: ProcessorMeta, kwargs: Record<string, unknown>) {
  return {
    class: meta.name,
    module_path: PROCESSOR_MODULE[meta.name] ?? "aqp.ml.processors",
    kwargs,
  };
}

function PipelineColumn({
  title,
  items,
  onRemove,
  onEdit,
  available,
  onAdd,
}: {
  title: string;
  items: { class: string; kwargs?: Record<string, unknown> }[];
  onRemove: (i: number) => void;
  onEdit: (i: number) => void;
  available: ProcessorMeta[];
  onAdd: (proc: ProcessorMeta) => void;
}) {
  return (
    <Card
      size="small"
      title={<Text strong>{title}</Text>}
      extra={
        <Select
          placeholder="+ Add"
          size="small"
          style={{ minWidth: 160 }}
          options={available.map((p) => ({ value: p.name, label: `${p.name} (${p.kind})` }))}
          onChange={(v) => {
            const meta = available.find((p) => p.name === v);
            if (meta) onAdd(meta);
          }}
        />
      }
    >
      {items.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No processors" />
      ) : (
        <Space direction="vertical" style={{ width: "100%" }} size={6}>
          {items.map((proc, i) => (
            <Card key={`${proc.class}-${i}`} size="small" styles={{ body: { padding: "6px 10px" } }}>
              <Space style={{ width: "100%", justifyContent: "space-between" }}>
                <div>
                  <Text strong>{proc.class}</Text>
                  <div style={{ fontSize: 11, opacity: 0.65, fontFamily: "monospace" }}>
                    {JSON.stringify(proc.kwargs ?? {}).slice(0, 80)}
                  </div>
                </div>
                <Space>
                  <Button size="small" onClick={() => onEdit(i)}>
                    Edit
                  </Button>
                  <Button size="small" danger icon={<DeleteOutlined />} onClick={() => onRemove(i)} />
                </Space>
              </Space>
            </Card>
          ))}
        </Space>
      )}
    </Card>
  );
}

export function MlDatasetDesigner() {
  const { message } = App.useApp();

  // ---------- Splits state ----------
  const [splitName, setSplitName] = useState("split_v1");
  const [splitMethod, setSplitMethod] = useState<"fixed" | "walk_forward" | "purged_kfold">(
    "fixed",
  );
  const [splitSymbols, setSplitSymbols] = useState<string[]>(["SPY", "AAPL", "MSFT"]);
  const [splitStart, setSplitStart] = useState("2018-01-01");
  const [splitEnd, setSplitEnd] = useState("2024-12-31");
  const [trainDays, setTrainDays] = useState<number>(1095);
  const [validDays, setValidDays] = useState<number>(180);
  const [testDays, setTestDays] = useState<number>(180);
  const [embargoDays, setEmbargoDays] = useState<number>(5);
  const [nFolds, setNFolds] = useState<number>(4);

  // ---------- Pipeline state ----------
  const [pipelineName, setPipelineName] = useState("pipeline_v1");
  const [pipelineDesc, setPipelineDesc] = useState("");
  const [shared, setShared] = useState<{ class: string; kwargs?: Record<string, unknown> }[]>([]);
  const [learn, setLearn] = useState<{ class: string; kwargs?: Record<string, unknown> }[]>([]);
  const [infer, setInfer] = useState<{ class: string; kwargs?: Record<string, unknown> }[]>([]);
  const [editing, setEditing] = useState<{
    bucket: "shared" | "learn" | "infer";
    index: number;
  } | null>(null);

  // ---------- Indicators state ----------
  const [pickedIndicators, setPickedIndicators] = useState<string[]>([]);
  const [pickedFundamentals, setPickedFundamentals] = useState<string[]>([]);
  const [featureSetName, setFeatureSetName] = useState("dataset_designer_set");

  const universe = useApiQuery<UniverseResponse>({
    queryKey: ["data", "universe", "designer"],
    path: "/data/universe",
    query: { limit: 500 },
    staleTime: 60_000,
  });
  const symbolOptions = (universe.data?.items ?? []).map((it) => ({
    value: it.vt_symbol ?? `${it.ticker ?? ""}.NASDAQ`,
    label: it.vt_symbol ?? it.ticker ?? "",
  }));

  const processors = useApiQuery<ProcessorMeta[]>({
    queryKey: ["ml", "processors"],
    path: "/ml/processors",
    staleTime: 5 * 60 * 1000,
  });

  const splits = useApiQuery<SplitPlanSummary[]>({
    queryKey: ["ml", "split-plans"],
    path: "/ml/split-plans",
    refetchInterval: 30_000,
  });

  const pipelines = useApiQuery<PipelineRecipeSummary[]>({
    queryKey: ["ml", "pipelines"],
    path: "/ml/pipelines",
    refetchInterval: 30_000,
  });

  const indicatorCatalog = useApiQuery<CatalogResponse>({
    queryKey: ["indicator-catalog"],
    path: "/data/indicators/catalog",
    staleTime: 5 * 60 * 1000,
  });
  const featureCandidates = useApiQuery<FeatureCandidatesResponse>({
    queryKey: ["feature-catalog", "candidates"],
    path: "/feature-catalog/candidates",
    query: { limit: 500 },
    staleTime: 5 * 60 * 1000,
  });

  const indicatorOptions = useMemo(() => {
    const all = (indicatorCatalog.data?.groups ?? []).flatMap((g) => g.indicators);
    return all.map((ind) => ({ value: ind.name, label: `${ind.name} — ${ind.group}` }));
  }, [indicatorCatalog.data]);

  const candidateOptions = useMemo(() => {
    return (featureCandidates.data?.candidates ?? []).map((c) => ({
      value: `${c.source}.${c.domain}.${c.field}`,
      label: `${c.field} (${c.source}.${c.domain})`,
    }));
  }, [featureCandidates.data]);

  const procsAvailable = processors.data ?? [];

  function addProcessor(bucket: "shared" | "learn" | "infer", meta: ProcessorMeta) {
    const spec = processorSpec(meta, defaultKwargs(meta));
    if (bucket === "shared") setShared((s) => [...s, spec]);
    if (bucket === "learn") setLearn((s) => [...s, spec]);
    if (bucket === "infer") setInfer((s) => [...s, spec]);
  }

  function removeFrom(bucket: "shared" | "learn" | "infer", i: number) {
    if (bucket === "shared") setShared((s) => s.filter((_, idx) => idx !== i));
    if (bucket === "learn") setLearn((s) => s.filter((_, idx) => idx !== i));
    if (bucket === "infer") setInfer((s) => s.filter((_, idx) => idx !== i));
  }

  function getBucket(b: "shared" | "learn" | "infer") {
    return b === "shared" ? shared : b === "learn" ? learn : infer;
  }
  function setBucket(b: "shared" | "learn" | "infer", v: { class: string; kwargs?: Record<string, unknown> }[]) {
    if (b === "shared") setShared(v);
    if (b === "learn") setLearn(v);
    if (b === "infer") setInfer(v);
  }

  async function saveSplit() {
    const config: Record<string, unknown> = {
      train_days: trainDays,
      valid_days: validDays,
      test_days: testDays,
      embargo_days: embargoDays,
      n_folds: nFolds,
    };
    try {
      await apiFetch("/ml/split-plans", {
        method: "POST",
        body: JSON.stringify({
          name: splitName,
          method: splitMethod,
          config,
          vt_symbols: splitSymbols,
          start: splitStart,
          end: splitEnd,
          interval: "1d",
        }),
      });
      message.success(`Saved split plan ${splitName}`);
      splits.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function savePipeline() {
    try {
      await apiFetch("/ml/pipelines", {
        method: "POST",
        body: JSON.stringify({
          name: pipelineName,
          description: pipelineDesc || null,
          shared_processors: shared,
          learn_processors: learn,
          infer_processors: infer,
          fit_window: {},
          tags: [],
        }),
      });
      message.success(`Saved pipeline ${pipelineName}`);
      pipelines.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function saveFeatureSet() {
    if (pickedIndicators.length === 0 && pickedFundamentals.length === 0) {
      message.warning("Pick at least one indicator or feed field");
      return;
    }
    const specs = [
      ...pickedIndicators,
      ...pickedFundamentals.map((f) => `Field:${f}`),
    ];
    try {
      await apiFetch("/feature-sets/", {
        method: "POST",
        body: JSON.stringify({
          name: featureSetName,
          description: "Generated from ML Dataset Designer",
          kind: "composite",
          specs,
          default_lookback_days: 60,
          tags: ["dataset-designer"],
        }),
      });
      message.success(`Saved feature set ${featureSetName}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="ML Dataset Designer"
      subtitle="Author splits, preprocessing pipelines, and feature sets visually."
    >
      <Tabs
        items={[
          {
            key: "splits",
            label: "Splits",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={14}>
                  <Card title="Configure split plan" size="small">
                    <Form layout="vertical">
                      <Row gutter={12}>
                        <Col xs={12}>
                          <Form.Item label="Name">
                            <Input value={splitName} onChange={(e) => setSplitName(e.target.value)} />
                          </Form.Item>
                        </Col>
                        <Col xs={12}>
                          <Form.Item label="Method">
                            <Select
                              value={splitMethod}
                              onChange={(v) => setSplitMethod(v)}
                              options={[
                                { value: "fixed", label: "Fixed" },
                                { value: "walk_forward", label: "Walk-forward" },
                                { value: "purged_kfold", label: "Purged k-fold" },
                              ]}
                            />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Form.Item label="Symbols">
                        <Select
                          mode="multiple"
                          value={splitSymbols}
                          onChange={setSplitSymbols}
                          options={
                            symbolOptions.length
                              ? symbolOptions
                              : splitSymbols.map((s) => ({ value: s, label: s }))
                          }
                          maxTagCount={6}
                        />
                      </Form.Item>
                      <Row gutter={12}>
                        <Col xs={12}>
                          <Form.Item label="Start">
                            <Input value={splitStart} onChange={(e) => setSplitStart(e.target.value)} />
                          </Form.Item>
                        </Col>
                        <Col xs={12}>
                          <Form.Item label="End">
                            <Input value={splitEnd} onChange={(e) => setSplitEnd(e.target.value)} />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Row gutter={12}>
                        <Col xs={6}>
                          <Form.Item label="Train days">
                            <InputNumber min={1} value={trainDays} onChange={(v) => setTrainDays(Number(v))} style={{ width: "100%" }} />
                          </Form.Item>
                        </Col>
                        <Col xs={6}>
                          <Form.Item label="Valid days">
                            <InputNumber min={0} value={validDays} onChange={(v) => setValidDays(Number(v))} style={{ width: "100%" }} />
                          </Form.Item>
                        </Col>
                        <Col xs={6}>
                          <Form.Item label="Test days">
                            <InputNumber min={1} value={testDays} onChange={(v) => setTestDays(Number(v))} style={{ width: "100%" }} />
                          </Form.Item>
                        </Col>
                        <Col xs={6}>
                          <Form.Item label="Embargo days">
                            <InputNumber min={0} value={embargoDays} onChange={(v) => setEmbargoDays(Number(v))} style={{ width: "100%" }} />
                          </Form.Item>
                        </Col>
                      </Row>
                      {splitMethod !== "fixed" ? (
                        <Form.Item label="Folds">
                          <InputNumber min={2} max={20} value={nFolds} onChange={(v) => setNFolds(Number(v))} />
                        </Form.Item>
                      ) : null}
                      <Button type="primary" icon={<SaveOutlined />} onClick={saveSplit}>
                        Save split plan
                      </Button>
                    </Form>
                  </Card>
                </Col>
                <Col xs={24} lg={10}>
                  <Card title="Saved split plans" size="small">
                    <Table
                      size="small"
                      rowKey="id"
                      dataSource={splits.data ?? []}
                      pagination={{ pageSize: 10 }}
                      columns={[
                        { title: "Name", dataIndex: "name" },
                        { title: "Method", dataIndex: "method" },
                        { title: "Folds", render: (_, r) => r.artifacts?.length ?? 0 },
                        { title: "Created", dataIndex: "created_at" },
                      ]}
                    />
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: "pipeline",
            label: "Pipeline",
            children: (
              <>
                {processors.error ? <Alert type="error" message={processors.error.message} /> : null}
                <Card size="small" style={{ marginBottom: 16 }}>
                  <Space wrap>
                    <Input
                      placeholder="Pipeline name"
                      value={pipelineName}
                      onChange={(e) => setPipelineName(e.target.value)}
                      style={{ width: 220 }}
                    />
                    <Input
                      placeholder="Description"
                      value={pipelineDesc}
                      onChange={(e) => setPipelineDesc(e.target.value)}
                      style={{ width: 320 }}
                    />
                    <Button type="primary" icon={<SaveOutlined />} onClick={savePipeline}>
                      Save pipeline
                    </Button>
                  </Space>
                </Card>
                <Row gutter={16}>
                  <Col xs={24} lg={8}>
                    <PipelineColumn
                      title="Shared (always)"
                      items={shared}
                      available={procsAvailable}
                      onAdd={(p) => addProcessor("shared", p)}
                      onRemove={(i) => removeFrom("shared", i)}
                      onEdit={(i) => setEditing({ bucket: "shared", index: i })}
                    />
                  </Col>
                  <Col xs={24} lg={8}>
                    <PipelineColumn
                      title="Learn (training only)"
                      items={learn}
                      available={procsAvailable}
                      onAdd={(p) => addProcessor("learn", p)}
                      onRemove={(i) => removeFrom("learn", i)}
                      onEdit={(i) => setEditing({ bucket: "learn", index: i })}
                    />
                  </Col>
                  <Col xs={24} lg={8}>
                    <PipelineColumn
                      title="Infer (inference only)"
                      items={infer}
                      available={procsAvailable}
                      onAdd={(p) => addProcessor("infer", p)}
                      onRemove={(i) => removeFrom("infer", i)}
                      onEdit={(i) => setEditing({ bucket: "infer", index: i })}
                    />
                  </Col>
                </Row>
                <Card title="Saved pipelines" size="small" style={{ marginTop: 16 }}>
                  <Table
                    size="small"
                    rowKey="id"
                    dataSource={pipelines.data ?? []}
                    pagination={{ pageSize: 10 }}
                    columns={[
                      { title: "Name", dataIndex: "name" },
                      { title: "Version", dataIndex: "version" },
                      {
                        title: "Steps",
                        render: (_, r) =>
                          (r.shared_processors?.length ?? 0) +
                          (r.learn_processors?.length ?? 0) +
                          (r.infer_processors?.length ?? 0),
                      },
                      { title: "Created", dataIndex: "created_at" },
                    ]}
                  />
                </Card>
                <Drawer
                  open={Boolean(editing)}
                  onClose={() => setEditing(null)}
                  title={editing ? `Edit ${getBucket(editing.bucket)[editing.index]?.class}` : ""}
                  width={420}
                >
                  {editing ? (
                    <Form layout="vertical">
                      <Form.Item label="kwargs (JSON)">
                        <Input.TextArea
                          autoSize={{ minRows: 6, maxRows: 18 }}
                          style={{ fontFamily: "monospace" }}
                          value={JSON.stringify(getBucket(editing.bucket)[editing.index]?.kwargs ?? {}, null, 2)}
                          onChange={(e) => {
                            try {
                              const next = JSON.parse(e.target.value) as Record<string, unknown>;
                              const list = [...getBucket(editing.bucket)];
                              const target = list[editing.index];
                              if (target) {
                                list[editing.index] = { class: target.class, kwargs: next };
                                setBucket(editing.bucket, list);
                              }
                            } catch {
                              /* ignore */
                            }
                          }}
                        />
                      </Form.Item>
                    </Form>
                  ) : null}
                </Drawer>
              </>
            ),
          },
          {
            key: "indicators",
            label: "Indicators & features",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={12}>
                  <Card title="Indicators (TA-Lib catalog)" size="small">
                    <Select
                      mode="multiple"
                      value={pickedIndicators}
                      onChange={setPickedIndicators}
                      options={indicatorOptions}
                      style={{ width: "100%" }}
                      placeholder="Pick indicators"
                      showSearch
                      filterOption={(input, option) =>
                        String(option?.label ?? "")
                          .toLowerCase()
                          .includes(input.toLowerCase())
                      }
                    />
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {pickedIndicators.length} selected
                      </Text>
                    </div>
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title="Feed fields (Alpha Vantage / FRED / GDelt)" size="small">
                    <Select
                      mode="multiple"
                      value={pickedFundamentals}
                      onChange={setPickedFundamentals}
                      options={candidateOptions}
                      style={{ width: "100%" }}
                      placeholder="Pick feed fields"
                      showSearch
                      filterOption={(input, option) =>
                        String(option?.label ?? "")
                          .toLowerCase()
                          .includes(input.toLowerCase())
                      }
                    />
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {pickedFundamentals.length} selected
                      </Text>
                    </div>
                  </Card>
                </Col>
                <Col xs={24} style={{ marginTop: 16 }}>
                  <Card size="small">
                    <Space>
                      <Input
                        value={featureSetName}
                        onChange={(e) => setFeatureSetName(e.target.value)}
                        placeholder="Feature set name"
                        style={{ width: 240 }}
                      />
                      <Button type="primary" icon={<PlusOutlined />} onClick={saveFeatureSet}>
                        Save as feature set
                      </Button>
                      <Tag color="blue">{pickedIndicators.length + pickedFundamentals.length} items</Tag>
                    </Space>
                  </Card>
                </Col>
              </Row>
            ),
          },
        ]}
      />
    </PageContainer>
  );
}
