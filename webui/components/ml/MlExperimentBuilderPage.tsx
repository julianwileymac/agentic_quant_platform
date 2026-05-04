"use client";

import { ExperimentOutlined, PlayCircleOutlined, ToolOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
} from "antd";
import { useState } from "react";

import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";

import { ML_EXPERIMENT_ACCENTS, ML_EXPERIMENT_PALETTE } from "./mlExperimentPalette";
import { dispatchFromGraph, serializeFlowPreview } from "./mlExperimentSerializer";

interface FrameworkCatalog {
  frameworks: { id: string; extra: string; models: string[] }[];
}

interface FlowPreviewResult {
  flow: string;
  metrics?: Record<string, unknown>;
  rows?: Record<string, unknown>[];
}

interface FlowMeta {
  flow: string;
  label: string;
  description: string;
  fields: { name: string; type: string; default?: unknown; options?: string[] }[];
}

const INITIAL_GRAPH: FlowGraph = {
  domain: "ml",
  version: 1,
  nodes: [
    {
      id: "dataset",
      type: "aqp",
      position: { x: 80, y: 120 },
      data: {
        kind: "Dataset",
        label: "Dataset",
        params: ML_EXPERIMENT_PALETTE[0]?.items[0]?.defaultParams ?? {},
      },
    },
    {
      id: "model",
      type: "aqp",
      position: { x: 420, y: 120 },
      data: {
        kind: "Model",
        label: "Model",
        params: ML_EXPERIMENT_PALETTE[3]?.items[0]?.defaultParams ?? {},
      },
    },
    {
      id: "experiment",
      type: "aqp",
      position: { x: 760, y: 120 },
      data: {
        kind: "Experiment",
        label: "Experiment",
        params: ML_EXPERIMENT_PALETTE[5]?.items[0]?.defaultParams ?? {},
      },
    },
  ],
  edges: [
    { id: "dataset-model", source: "dataset", target: "model" },
    { id: "model-experiment", source: "model", target: "experiment" },
  ],
};

export function MlExperimentBuilderPage() {
  const { message } = App.useApp();
  const [taskId, setTaskId] = useState<string | null>(null);
  const [preview, setPreview] = useState<FlowPreviewResult | null>(null);
  const [workbenchOpen, setWorkbenchOpen] = useState(false);
  const [workbenchFlow, setWorkbenchFlow] = useState<string>("linear");
  const [workbenchParams, setWorkbenchParams] = useState<Record<string, unknown>>({});
  const [workbenchResult, setWorkbenchResult] = useState<FlowPreviewResult | null>(null);
  const [workbenchLoading, setWorkbenchLoading] = useState(false);

  const stream = useChatStream(taskId);

  const frameworks = useApiQuery<FrameworkCatalog>({
    queryKey: ["ml", "frameworks"],
    path: "/ml/frameworks",
    staleTime: 5 * 60 * 1000,
  });

  const flowsCatalog = useApiQuery<FlowMeta[]>({
    queryKey: ["ml", "flows"],
    path: "/ml/flows",
    staleTime: 5 * 60 * 1000,
  });

  async function runGraph(graph: FlowGraph) {
    try {
      const dispatch = dispatchFromGraph(graph);
      if (dispatch.kind === "test_single" || dispatch.kind === "test_scenario") {
        const result = await apiFetch<Record<string, unknown>>(dispatch.endpoint, {
          method: "POST",
          body: JSON.stringify(dispatch.payload),
        });
        message.success(`${dispatch.kind} complete`);
        setPreview({ flow: dispatch.kind, rows: [result] });
        return;
      }
      const res = await apiFetch<{ task_id: string }>(dispatch.endpoint, {
        method: "POST",
        body: JSON.stringify(dispatch.payload),
      });
      setTaskId(res.task_id);
      message.success(`${dispatch.kind} queued (${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function previewFlow(graph: FlowGraph) {
    const { flow, payload } = serializeFlowPreview(graph);
    const res = await apiFetch<FlowPreviewResult>(`/ml/flows/${flow}/preview`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setPreview(res);
    message.success(`${flow} preview complete`);
  }

  async function runWorkbench() {
    setWorkbenchLoading(true);
    setWorkbenchResult(null);
    try {
      // Default to the dataset_cfg from the canvas if the user hasn't supplied one.
      const dataset_cfg = (workbenchParams.dataset_cfg as Record<string, unknown>) ?? undefined;
      const payload = {
        ...workbenchParams,
        dataset_cfg: dataset_cfg ?? {},
      };
      const res = await apiFetch<FlowPreviewResult>(`/ml/flows/${workbenchFlow}/preview`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setWorkbenchResult(res);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setWorkbenchLoading(false);
    }
  }

  const activeFlowMeta = (flowsCatalog.data ?? []).find((f) => f.flow === workbenchFlow);

  return (
    <PageContainer
      title="ML Experiment Builder"
      subtitle="Compose datasets, preprocessing, model definitions, experiment records, and quick tests as a graph."
    >
      <Tabs
        items={[
          {
            key: "builder",
            label: "Builder",
            children: (
              <Row gutter={16}>
                <Col xs={24} xxl={18}>
                  <WorkflowEditor
                    domain="ml"
                    initialGraph={INITIAL_GRAPH}
                    paletteSections={ML_EXPERIMENT_PALETTE}
                    accentByKind={ML_EXPERIMENT_ACCENTS}
                    onRun={runGraph}
                    height="calc(100vh - 220px)"
                    toolbarExtras={
                      <Space>
                        <Button
                          icon={<ToolOutlined />}
                          onClick={() => setWorkbenchOpen(true)}
                        >
                          Interactive Workbench
                        </Button>
                        <Button
                          icon={<PlayCircleOutlined />}
                          onClick={() => message.info("Use Run to submit the graph")}
                        >
                          Submit
                        </Button>
                      </Space>
                    }
                  />
                </Col>
                <Col xs={24} xxl={6}>
                  <Space direction="vertical" style={{ width: "100%" }} size="middle">
                    <Card title="Framework Catalog" size="small">
                      <Space wrap>
                        {(frameworks.data?.frameworks ?? []).map((fw) => (
                          <Tag key={fw.id} color="blue">
                            {fw.id} · {fw.models.length}
                          </Tag>
                        ))}
                      </Space>
                    </Card>
                    <Card title="Task Stream" size="small">
                      {taskId ? (
                        <Descriptions size="small" column={1}>
                          <Descriptions.Item label="Task">{taskId}</Descriptions.Item>
                          <Descriptions.Item label="Status">{stream.status}</Descriptions.Item>
                          <Descriptions.Item label="Events">{stream.events.length}</Descriptions.Item>
                        </Descriptions>
                      ) : (
                        <Alert type="info" message="Run the graph to queue an ML experiment." showIcon />
                      )}
                    </Card>
                  </Space>
                </Col>
              </Row>
            ),
          },
          {
            key: "preview",
            label: "Interactive Preview",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={10}>
                  <Card
                    title="Flow Preview"
                    extra={<ExperimentOutlined />}
                    actions={[
                      <Button key="hint" type="link">
                        Add a FlowPreview node, then use graph JSON export to keep the recipe.
                      </Button>,
                    ]}
                  >
                    <Alert
                      type="info"
                      showIcon
                      message="Use the canvas context menu to add a FlowPreview node, then run preview from an exported graph in a follow-up iteration."
                    />
                  </Card>
                </Col>
                <Col xs={24} lg={14}>
                  <Card
                    title="Latest Preview"
                    extra={
                      <Button
                        onClick={() => previewFlow(INITIAL_GRAPH)}
                        icon={<PlayCircleOutlined />}
                      >
                        Preview Default Linear Flow
                      </Button>
                    }
                  >
                    {preview ? (
                      <>
                        <Descriptions size="small" column={2}>
                          <Descriptions.Item label="Flow">{preview.flow}</Descriptions.Item>
                          <Descriptions.Item label="Metrics">
                            {Object.keys(preview.metrics ?? {}).length}
                          </Descriptions.Item>
                        </Descriptions>
                        <Table
                          size="small"
                          rowKey={(_, idx) => String(idx)}
                          dataSource={preview.rows ?? []}
                          columns={Object.keys(preview.rows?.[0] ?? {}).map((key) => ({
                            key,
                            dataIndex: key,
                            title: key,
                          }))}
                          pagination={{ pageSize: 8 }}
                        />
                      </>
                    ) : (
                      <Alert type="info" message="No preview run yet." showIcon />
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
        ]}
      />

      <Drawer
        title="Interactive ML Workbench"
        placement="right"
        width={520}
        open={workbenchOpen}
        onClose={() => setWorkbenchOpen(false)}
      >
        <Form layout="vertical">
          <Form.Item label="Flow">
            <Select
              value={workbenchFlow}
              onChange={(v) => {
                setWorkbenchFlow(v);
                setWorkbenchParams({});
                setWorkbenchResult(null);
              }}
              options={(flowsCatalog.data ?? []).map((f) => ({
                value: f.flow,
                label: `${f.label} (${f.flow})`,
              }))}
            />
          </Form.Item>
          {activeFlowMeta?.description ? (
            <Alert type="info" showIcon message={activeFlowMeta.description} style={{ marginBottom: 12 }} />
          ) : null}
          {(activeFlowMeta?.fields ?? []).map((field) => {
            const value = workbenchParams[field.name] ?? field.default;
            const setValue = (v: unknown) =>
              setWorkbenchParams((prev) => ({ ...prev, [field.name]: v }));
            if (field.type === "select" && Array.isArray(field.options)) {
              return (
                <Form.Item key={field.name} label={field.name}>
                  <Select
                    value={value as string}
                    onChange={setValue}
                    options={field.options.map((o) => ({ value: o, label: o }))}
                  />
                </Form.Item>
              );
            }
            if (field.type === "integer" || field.type === "number") {
              return (
                <Form.Item key={field.name} label={field.name}>
                  <InputNumber
                    value={value as number}
                    onChange={(v) => setValue(v)}
                    style={{ width: "100%" }}
                  />
                </Form.Item>
              );
            }
            if (field.type === "list") {
              return (
                <Form.Item key={field.name} label={field.name}>
                  <Select
                    mode="tags"
                    value={Array.isArray(value) ? (value as string[]) : []}
                    onChange={(v) => setValue(v)}
                  />
                </Form.Item>
              );
            }
            return (
              <Form.Item key={field.name} label={field.name}>
                <Input
                  value={(value as string | undefined) ?? ""}
                  onChange={(e) => setValue(e.target.value)}
                />
              </Form.Item>
            );
          })}
          <Button type="primary" loading={workbenchLoading} onClick={runWorkbench}>
            Run flow
          </Button>
        </Form>
        {workbenchResult ? (
          <Card title="Result" size="small" style={{ marginTop: 16 }}>
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="Flow">{workbenchResult.flow}</Descriptions.Item>
              {Object.entries(workbenchResult.metrics ?? {}).map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>
                  {typeof v === "number" ? v.toFixed(4) : String(v)}
                </Descriptions.Item>
              ))}
            </Descriptions>
            {workbenchResult.rows && workbenchResult.rows.length > 0 ? (
              <Table
                size="small"
                rowKey={(_, idx) => String(idx)}
                dataSource={workbenchResult.rows.slice(0, 50)}
                columns={Object.keys(workbenchResult.rows[0] ?? {}).map((key) => ({
                  key,
                  dataIndex: key,
                  title: key,
                }))}
                pagination={false}
                scroll={{ y: 240 }}
              />
            ) : null}
          </Card>
        ) : null}
      </Drawer>
    </PageContainer>
  );
}
