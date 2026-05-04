"use client";

import { ExportOutlined, PlayCircleOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  Row,
  Select,
  Space,
  Switch,
  Tabs,
  Tag,
  Typography,
} from "antd";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
});

const { Paragraph, Text } = Typography;

interface RecipeSummary {
  id: string;
  name: string;
  description?: string;
  group: string;
  path: string;
  model_class?: string | null;
  dataset_class?: string | null;
}

interface RecipeBody {
  id: string;
  body: Record<string, unknown>;
  dataset_cfg: Record<string, unknown>;
  model_cfg: Record<string, unknown>;
  records: unknown[];
}

interface SplitPlanSummary {
  id: string;
  name: string;
}

interface PipelineRecipeSummary {
  id: string;
  name: string;
  version: number;
}

interface RegistryDetailLite {
  alias: string;
  module?: string | null;
  qualname: string;
}

const DEFAULT_DATASET = JSON.stringify(
  {
    class: "DatasetH",
    module_path: "aqp.ml.dataset",
    kwargs: {
      handler: {
        class: "Alpha158",
        module_path: "aqp.ml.features.alpha158",
        kwargs: {
          instruments: ["SPY", "AAPL", "MSFT", "GOOGL"],
          start_time: "2018-01-01",
          end_time: "2024-12-31",
        },
      },
      segments: {
        train: ["2018-01-01", "2021-12-31"],
        valid: ["2022-01-01", "2022-12-31"],
        test: ["2023-01-01", "2024-12-31"],
      },
    },
  },
  null,
  2,
);

const DEFAULT_MODEL = JSON.stringify(
  {
    class: "LGBModel",
    module_path: "aqp.ml.models.tree",
    kwargs: {
      num_leaves: 63,
      learning_rate: 0.05,
      n_estimators: 500,
    },
  },
  null,
  2,
);

const DEFAULT_RECORDS = JSON.stringify(
  [
    { class: "SignalRecord", module_path: "aqp.ml.recorder", kwargs: {} },
    { class: "SigAnaRecord", module_path: "aqp.ml.recorder", kwargs: { horizons: [1, 5, 10] } },
  ],
  null,
  2,
);

export function MlTrainingPage() {
  const searchParams = useSearchParams();
  const prefillModelAlias = searchParams.get("model");
  const prefillDatasetPreset = searchParams.get("datasetPreset");
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [datasetText, setDatasetText] = useState(DEFAULT_DATASET);
  const [modelText, setModelText] = useState(DEFAULT_MODEL);
  const [recordsText, setRecordsText] = useState(DEFAULT_RECORDS);
  const [recipeId, setRecipeId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [prefillNotice, setPrefillNotice] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  const recipes = useApiQuery<RecipeSummary[]>({
    queryKey: ["ml", "recipes"],
    path: "/ml/recipes",
    staleTime: 5 * 60 * 1000,
  });

  const recipeBody = useApiQuery<RecipeBody>({
    queryKey: ["ml", "recipe", recipeId ?? ""],
    path: recipeId ? `/ml/recipes/${recipeId}` : "/ml/recipes",
    enabled: Boolean(recipeId),
  });

  const splits = useApiQuery<SplitPlanSummary[]>({
    queryKey: ["ml", "split-plans"],
    path: "/ml/split-plans",
  });
  const pipelines = useApiQuery<PipelineRecipeSummary[]>({
    queryKey: ["ml", "pipelines"],
    path: "/ml/pipelines",
  });

  useEffect(() => {
    if (!recipeBody.data) return;
    setDatasetText(JSON.stringify(recipeBody.data.dataset_cfg, null, 2));
    setModelText(JSON.stringify(recipeBody.data.model_cfg, null, 2));
    setRecordsText(JSON.stringify(recipeBody.data.records ?? [], null, 2));
  }, [recipeBody.data]);

  useEffect(() => {
    let cancelled = false;
    if (!prefillModelAlias || recipeId) return;
    (async () => {
      try {
        const detail = await apiFetch<RegistryDetailLite>(
          `/registry/model/${encodeURIComponent(prefillModelAlias)}`,
        );
        if (cancelled) return;
        const nextModel = JSON.parse(DEFAULT_MODEL) as Record<string, unknown>;
        nextModel.class = detail.alias;
        const inferredModule =
          detail.module ||
          detail.qualname.split(".").slice(0, -1).join(".");
        if (inferredModule) nextModel.module_path = inferredModule;
        setModelText(JSON.stringify(nextModel, null, 2));
        if (prefillDatasetPreset) {
          form.setFieldValue(
            "run_name",
            `train_${prefillModelAlias.toLowerCase()}_${prefillDatasetPreset.toLowerCase()}`,
          );
        }
        setPrefillNotice(
          `Prefilled model from zoo: ${prefillModelAlias}${
            prefillDatasetPreset ? ` · dataset preset hint: ${prefillDatasetPreset}` : ""
          }`,
        );
      } catch {
        if (!cancelled) {
          setPrefillNotice(`Unable to prefill model ${prefillModelAlias} from registry.`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [prefillDatasetPreset, prefillModelAlias, recipeId, form]);

  useEffect(() => {
    if (!prefillDatasetPreset || prefillModelAlias || recipeId) return;
    form.setFieldValue("run_name", `train_${prefillDatasetPreset.toLowerCase()}`);
    setPrefillNotice(`Dataset preset hint from library: ${prefillDatasetPreset}`);
  }, [prefillDatasetPreset, prefillModelAlias, recipeId, form]);

  async function submit() {
    const v = await form.validateFields();
    let dataset_cfg: unknown;
    let model_cfg: unknown;
    let records: unknown;
    try {
      dataset_cfg = JSON.parse(datasetText);
    } catch (err) {
      message.error(`dataset_cfg not valid JSON: ${(err as Error).message}`);
      return;
    }
    try {
      model_cfg = JSON.parse(modelText);
    } catch (err) {
      message.error(`model_cfg not valid JSON: ${(err as Error).message}`);
      return;
    }
    try {
      records = JSON.parse(recordsText);
    } catch (err) {
      message.error(`records not valid JSON: ${(err as Error).message}`);
      return;
    }
    try {
      const res = await apiFetch<{ task_id: string }>("/ml/train", {
        method: "POST",
        body: JSON.stringify({
          dataset_cfg,
          model_cfg,
          records: Array.isArray(records) ? records : [],
          run_name: v.run_name,
          register_alpha: Boolean(v.register_alpha),
          split_plan_id: v.split_plan_id || null,
          pipeline_recipe_id: v.pipeline_recipe_id || null,
        }),
      });
      setTaskId(res.task_id);
      message.success(`Training queued (${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function exportToKafka() {
    const v = await form.validateFields();
    if (!v.pipeline_recipe_id) {
      message.warning("Pick a saved pipeline first");
      return;
    }
    try {
      const res = await apiFetch<{ topic: string; submitted: boolean; error?: string }>(
        `/ml/pipelines/${v.pipeline_recipe_id}/export`,
        { method: "POST", body: JSON.stringify({}) },
      );
      if (res.submitted) {
        message.success(`Exported pipeline → ${res.topic}`);
      } else {
        message.warning(`Compiled but not submitted: ${res.error ?? "streaming runtime unavailable"}`);
      }
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="ML Training"
      subtitle="Submit a Qlib-style ML pipeline and stream progress."
    >
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Text strong>Recipe</Text>
          <Select
            placeholder="Pick a recipe"
            value={recipeId ?? undefined}
            onChange={(v) => setRecipeId(v)}
            style={{ minWidth: 380 }}
            showSearch
            filterOption={(input, option) =>
              String(option?.label ?? "")
                .toLowerCase()
                .includes(input.toLowerCase())
            }
            options={(recipes.data ?? []).map((r) => ({
              value: r.id,
              label: `${r.group}/${r.name} ${r.model_class ? `· ${r.model_class}` : ""}`,
            }))}
          />
          {recipeBody.data ? (
            <Tag color="blue">loaded {recipeBody.data.id}</Tag>
          ) : null}
        </Space>
        {prefillNotice ? (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 12 }}
            message={prefillNotice}
          />
        ) : null}
      </Card>
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="Run" size="small">
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                run_name: "lgbm_alpha158",
                register_alpha: true,
                split_plan_id: null,
                pipeline_recipe_id: null,
              }}
            >
              <Form.Item label="Run name" name="run_name" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item label="Register as alpha" name="register_alpha" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item label="Split plan (optional)" name="split_plan_id">
                <Select
                  allowClear
                  options={(splits.data ?? []).map((s) => ({
                    value: s.id,
                    label: s.name,
                  }))}
                />
              </Form.Item>
              <Form.Item label="Pipeline recipe (optional)" name="pipeline_recipe_id">
                <Select
                  allowClear
                  options={(pipelines.data ?? []).map((p) => ({
                    value: p.id,
                    label: `${p.name} v${p.version}`,
                  }))}
                />
              </Form.Item>
              <Space>
                <Button type="primary" icon={<PlayCircleOutlined />} onClick={submit}>
                  Train
                </Button>
                <Button icon={<ExportOutlined />} onClick={exportToKafka}>
                  Export to Kafka
                </Button>
              </Space>
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
          <Card size="small">
            <Tabs
              items={[
                {
                  key: "dataset",
                  label: "dataset_cfg",
                  children: (
                    <div style={{ height: 360 }}>
                      <MonacoEditor
                        height="100%"
                        defaultLanguage="json"
                        value={datasetText}
                        onChange={(v) => setDatasetText(v ?? "")}
                        theme="vs-dark"
                        options={{ fontSize: 13, minimap: { enabled: false } }}
                      />
                    </div>
                  ),
                },
                {
                  key: "model",
                  label: "model_cfg",
                  children: (
                    <div style={{ height: 360 }}>
                      <MonacoEditor
                        height="100%"
                        defaultLanguage="json"
                        value={modelText}
                        onChange={(v) => setModelText(v ?? "")}
                        theme="vs-dark"
                        options={{ fontSize: 13, minimap: { enabled: false } }}
                      />
                    </div>
                  ),
                },
                {
                  key: "records",
                  label: "records",
                  children: (
                    <div style={{ height: 360 }}>
                      <MonacoEditor
                        height="100%"
                        defaultLanguage="json"
                        value={recordsText}
                        onChange={(v) => setRecordsText(v ?? "")}
                        theme="vs-dark"
                        options={{ fontSize: 13, minimap: { enabled: false } }}
                      />
                    </div>
                  ),
                },
              ]}
            />
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
