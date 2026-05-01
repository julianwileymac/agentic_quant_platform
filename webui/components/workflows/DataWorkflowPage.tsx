"use client";

import {
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { DATA_PALETTE } from "@/components/flow/palettes";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import { serializeDataPipeline } from "@/components/flow/serializers";
import type { FlowGraph } from "@/components/flow/types";
import { apiFetch } from "@/lib/api/client";

const ACCENTS: Record<string, string> = {
  Template: "#14b8a6",
  Source: "#10b981",
  Plan: "#0ea5e9",
  Load: "#6366f1",
  Transform: "#3b82f6",
  Feature: "#a855f7",
  Dbt: "#ff694b",
  Iceberg: "#f59e0b",
  Parquet: "#f59e0b",
  Index: "#f59e0b",
  Live: "#ef4444",
};

const DEFAULT_TEMPLATE_ID = "alpha-vantage-intraday-2y-all-active";

interface LoadingTemplateField {
  name: string;
  label: string;
  kind: "string" | "number" | "boolean" | "select" | "json";
  path: Array<string | number>;
  description?: string | null;
  default?: unknown;
  required?: boolean;
  options?: string[];
}

interface LoadingTemplate {
  id: string;
  title: string;
  description: string;
  category: string;
  provider?: string | null;
  endpoint: string;
  run_kind: string;
  tags: string[];
  default_payload: Record<string, unknown>;
  fields: LoadingTemplateField[];
  flow_graph: FlowGraph;
}

interface TemplateRunResponse {
  template_id: string;
  task_id?: string;
  stream_url?: string;
  dry_run?: boolean;
}

const STARTER_GRAPH: FlowGraph = {
  domain: "data",
  version: 1,
  nodes: [
    {
      id: "src-1",
      type: "aqp",
      position: { x: 80, y: 60 },
      data: {
        kind: "Source",
        label: "yfinance",
        params: { provider: "yahoo", symbols: ["SPY", "AAPL"], interval: "1d" },
      },
    },
    {
      id: "tx-1",
      type: "aqp",
      position: { x: 360, y: 60 },
      data: { kind: "Transform", label: "Adjust", params: { kind: "adjust" } },
    },
    {
      id: "snk-1",
      type: "aqp",
      position: { x: 640, y: 60 },
      data: { kind: "Parquet", label: "Lake parquet", params: { path: "data/parquet/" } },
    },
  ],
  edges: [
    { id: "e1", source: "src-1", target: "tx-1" },
    { id: "e2", source: "tx-1", target: "snk-1" },
  ],
};

export function DataWorkflowPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm<Record<string, unknown>>();
  const [templates, setTemplates] = useState<LoadingTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>(DEFAULT_TEMPLATE_ID);
  const [graph, setGraph] = useState<FlowGraph>(STARTER_GRAPH);
  const [editorKey, setEditorKey] = useState(0);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [runningTemplate, setRunningTemplate] = useState(false);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === selectedTemplateId) ?? templates[0],
    [selectedTemplateId, templates],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadTemplates() {
      setLoadingTemplates(true);
      try {
        const data = await apiFetch<LoadingTemplate[]>("/pipelines/templates");
        if (cancelled) return;
        setTemplates(data);
        const preferred = data.find((template) => template.id === DEFAULT_TEMPLATE_ID) ?? data[0];
        if (preferred) {
          setSelectedTemplateId(preferred.id);
          form.setFieldsValue(defaultFormValues(preferred) as Parameters<typeof form.setFieldsValue>[0]);
          setGraph(graphFromTemplate(preferred, {}));
          setEditorKey((key) => key + 1);
        }
      } catch (err) {
        if (!cancelled) {
          message.warning(`Template catalog unavailable: ${(err as Error).message}`);
        }
      } finally {
        if (!cancelled) setLoadingTemplates(false);
      }
    }
    void loadTemplates();
    return () => {
      cancelled = true;
    };
  }, [form, message]);

  function selectTemplate(templateId: string) {
    setSelectedTemplateId(templateId);
    const template = templates.find((candidate) => candidate.id === templateId);
    if (!template) return;
    form.setFieldsValue(defaultFormValues(template) as Parameters<typeof form.setFieldsValue>[0]);
    setGraph(graphFromTemplate(template, {}));
    setEditorKey((key) => key + 1);
  }

  async function applyTemplate() {
    if (!selectedTemplate) return;
    try {
      const values = await form.validateFields();
      const overrides = overridesFromValues(selectedTemplate, values);
      setGraph(graphFromTemplate(selectedTemplate, overrides));
      setEditorKey((key) => key + 1);
      message.success("Template applied to canvas");
    } catch (err) {
      message.error(`Could not apply template: ${(err as Error).message}`);
    }
  }

  async function queueSelectedTemplate() {
    if (!selectedTemplate) return;
    try {
      const values = await form.validateFields();
      const overrides = overridesFromValues(selectedTemplate, values);
      setRunningTemplate(true);
      const response = await queueTemplate(selectedTemplate.id, overrides);
      message.success(
        response.task_id
          ? `Queued ${selectedTemplate.title}: ${response.task_id}`
          : `Queued ${selectedTemplate.title}`,
      );
    } catch (err) {
      message.error(`Could not queue template: ${(err as Error).message}`);
    } finally {
      setRunningTemplate(false);
    }
  }

  async function run(graph: FlowGraph) {
    const payload = serializeDataPipeline(graph);
    const templateJobs = payload.jobs.filter((job) => job.kind === "Template");
    if (templateJobs.length) {
      const taskIds: string[] = [];
      for (const job of templateJobs) {
        const templateId = String(job.params.template_id ?? "");
        if (!templateId) {
          message.warning("Template nodes must include params.template_id");
          return;
        }
        const overrides = isRecord(job.params.overrides) ? job.params.overrides : {};
        const response = await queueTemplate(templateId, overrides);
        if (response.task_id) taskIds.push(response.task_id);
      }
      message.success(
        taskIds.length
          ? `Queued ${templateJobs.length} template job(s): ${taskIds.join(", ")}`
          : `Queued ${templateJobs.length} template job(s).`,
      );
      return;
    }

    const dbtJobs = payload.jobs.filter((job) => job.kind === "Dbt");
    if (dbtJobs.length) {
      for (const job of dbtJobs) {
        const select = Array.isArray(job.params.select) ? job.params.select.map(String) : ["tag:aqp_generated"];
        await apiFetch("/dbt/build", {
          method: "POST",
          body: JSON.stringify({ select }),
        });
      }
      message.success(`Ran ${dbtJobs.length} dbt build job(s).`);
      return;
    }

    const sourceJobs = payload.jobs.filter((j) => j.kind === "Source");
    if (sourceJobs.length === 0) {
      message.warning("Add at least one Template or Source node");
      return;
    }
    let queued = 0;
    const errors: string[] = [];
    for (const job of sourceJobs) {
      const symbols = (job.params.symbols as string[]) ?? [];
      try {
        await apiFetch("/data/ingest", {
          method: "POST",
          body: JSON.stringify({
            symbols,
            start: job.params.start ?? "2022-01-01",
            end: job.params.end ?? "2024-12-31",
            interval: job.params.interval ?? "1d",
            source: job.params.provider ?? "yahoo",
          }),
        });
        queued += 1;
      } catch (err) {
        errors.push((err as Error).message);
      }
    }
    if (errors.length) {
      message.error(`Queued ${queued}/${sourceJobs.length}: ${errors.join("; ")}`);
    } else {
      message.success(`Queued ${queued} ingest job(s).`);
    }
  }

  return (
    <PageContainer
      title="Data pipeline editor"
      subtitle="Visually wire sources → transforms → features → sinks."
      full
    >
      <div style={{ flex: 1, padding: "0 16px 16px" }}>
        <Card
          size="small"
          loading={loadingTemplates}
          style={{ marginBottom: 12 }}
          title={
            <Space wrap>
              <span>Loading templates</span>
              {selectedTemplate ? <Tag color="cyan">{selectedTemplate.run_kind}</Tag> : null}
            </Space>
          }
          extra={
            <Space>
              <Button onClick={applyTemplate} disabled={!selectedTemplate}>
                Apply to canvas
              </Button>
              <Button
                type="primary"
                onClick={queueSelectedTemplate}
                loading={runningTemplate}
                disabled={!selectedTemplate}
              >
                Queue template
              </Button>
            </Space>
          }
        >
          <Row gutter={[16, 12]}>
            <Col xs={24} lg={8}>
              <Select
                style={{ width: "100%" }}
                value={selectedTemplate?.id}
                onChange={selectTemplate}
                options={templates.map((template) => ({
                  value: template.id,
                  label: template.title,
                }))}
              />
              {selectedTemplate ? (
                <Typography.Paragraph type="secondary" style={{ margin: "8px 0 0" }}>
                  {selectedTemplate.description}
                </Typography.Paragraph>
              ) : null}
              <Space wrap>
                {selectedTemplate?.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}
              </Space>
            </Col>
            <Col xs={24} lg={16}>
              <Form form={form} layout="inline">
                {selectedTemplate?.fields.map((field) => (
                  <Form.Item
                    key={field.name}
                    name={field.name}
                    label={field.label}
                    valuePropName={field.kind === "boolean" ? "checked" : "value"}
                    rules={
                      field.required
                        ? [{ required: true, message: `${field.label} is required` }]
                        : undefined
                    }
                    style={{ marginBottom: 8 }}
                    tooltip={field.description ?? undefined}
                  >
                    {renderField(field)}
                  </Form.Item>
                ))}
              </Form>
            </Col>
          </Row>
        </Card>
        <WorkflowEditor
          key={editorKey}
          domain="data"
          paletteSections={DATA_PALETTE}
          initialGraph={graph}
          accentByKind={ACCENTS}
          onRun={run}
          height="calc(100vh - 340px)"
        />
      </div>
    </PageContainer>
  );
}

function renderField(field: LoadingTemplateField) {
  if (field.kind === "select") {
    return (
      <Select
        style={{ minWidth: 150 }}
        options={(field.options ?? []).map((value) => ({ value, label: value }))}
      />
    );
  }
  if (field.kind === "number") {
    return <InputNumber style={{ width: 140 }} min={1} />;
  }
  if (field.kind === "boolean") {
    return <Switch />;
  }
  if (field.kind === "json") {
    return <Input.TextArea style={{ width: 260 }} autoSize={{ minRows: 1, maxRows: 4 }} />;
  }
  return <Input style={{ width: 220 }} />;
}

async function queueTemplate(templateId: string, overrides: Record<string, unknown>): Promise<TemplateRunResponse> {
  return apiFetch<TemplateRunResponse>(`/pipelines/templates/${templateId}/run`, {
    method: "POST",
    body: JSON.stringify({ overrides }),
  });
}

function graphFromTemplate(template: LoadingTemplate, overrides: Record<string, unknown>): FlowGraph {
  const graph = structuredClone(template.flow_graph ?? STARTER_GRAPH) as FlowGraph;
  graph.nodes = graph.nodes.map((node) => {
    if (node.data.kind !== "Template") return node;
    const params = isRecord(node.data.params) ? node.data.params : {};
    return {
      ...node,
      data: {
        ...node.data,
        params: {
          ...params,
          template_id: template.id,
          overrides,
        },
      },
    };
  });
  return graph;
}

function defaultFormValues(template: LoadingTemplate): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const field of template.fields) {
    const value = readPath(template.default_payload, field.path) ?? field.default;
    values[field.name] = field.kind === "json" ? JSON.stringify(value ?? {}, null, 2) : value;
  }
  return values;
}

function overridesFromValues(template: LoadingTemplate, values: Record<string, unknown>): Record<string, unknown> {
  const overrides: Record<string, unknown> = {};
  for (const field of template.fields) {
    if (!field.path.length) continue;
    let value = values[field.name];
    if (field.kind === "json" && typeof value === "string") {
      value = value.trim() ? JSON.parse(value) : {};
    }
    writePath(overrides, field.path, value);
  }
  return overrides;
}

function readPath(source: Record<string, unknown>, path: Array<string | number>): unknown {
  let cursor: unknown = source;
  for (const part of path) {
    if (!isRecord(cursor)) return undefined;
    cursor = cursor[String(part)];
  }
  return cursor;
}

function writePath(target: Record<string, unknown>, path: Array<string | number>, value: unknown) {
  let cursor = target;
  for (const [index, part] of path.entries()) {
    const key = String(part);
    if (index === path.length - 1) {
      cursor[key] = value;
      return;
    }
    if (!isRecord(cursor[key])) {
      cursor[key] = {};
    }
    cursor = cursor[key] as Record<string, unknown>;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
