"use client";

import { DeleteOutlined, ExperimentOutlined, PlusOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
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
import {
  useFeatureSet,
  useFeatureSets,
  useFeatureSetUsages,
  useFeatureSetVersions,
  type FeatureSetPreviewResp,
  type FeatureSetSummary,
} from "@/lib/api/featureSets";

interface IndicatorEntry {
  id: string;
  name: string;
  group: string;
  description: string;
  outputs: string[];
  params: { name: string; default: number | string | null; type: string }[];
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
  frequency?: string;
}

interface FeatureCandidatesResponse {
  candidates: FeatureCandidate[];
}

const { Text, Paragraph, Title } = Typography;

const KIND_OPTIONS = [
  { value: "indicator", label: "Indicator bundle" },
  { value: "model_pred", label: "Model predictions" },
  { value: "composite", label: "Composite (mixed)" },
];

export function FeatureSetWorkbench() {
  const { message, modal } = App.useApp();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [previewSymbols, setPreviewSymbols] = useState<string[]>(["AAPL", "MSFT"]);
  const [previewStart, setPreviewStart] = useState("2024-01-01");
  const [previewEnd, setPreviewEnd] = useState("2024-06-30");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<FeatureSetPreviewResp | null>(null);
  const [picker, setPicker] = useState<"indicators" | "candidates" | null>(null);

  const list = useFeatureSets();
  const detail = useFeatureSet(selectedId);
  const versions = useFeatureSetVersions(selectedId);
  const usages = useFeatureSetUsages(selectedId);

  const indicatorCatalog = useApiQuery<CatalogResponse>({
    queryKey: ["indicator-catalog"],
    path: "/data/indicators/catalog",
    enabled: picker === "indicators",
    staleTime: 5 * 60 * 1000,
  });

  const featureCandidates = useApiQuery<FeatureCandidatesResponse>({
    queryKey: ["feature-catalog", "candidates"],
    path: "/feature-catalog/candidates",
    enabled: picker === "candidates",
    staleTime: 5 * 60 * 1000,
  });

  const items = useMemo(() => list.data ?? [], [list.data]);

  const [form] = Form.useForm();
  const [createForm] = Form.useForm();

  const selected = detail.data;

  // Sync form values when selection changes.
  const formInitial = useMemo(() => {
    if (!selected) return undefined;
    return {
      description: selected.description,
      kind: selected.kind,
      specs: (selected.specs ?? []).join("\n"),
      default_lookback_days: selected.default_lookback_days,
      tags: selected.tags ?? [],
    };
  }, [selected]);

  if (formInitial) {
    form.setFieldsValue(formInitial);
  }

  async function save() {
    if (!selectedId) return;
    const v = await form.validateFields();
    const specs = String(v.specs ?? "")
      .split(/\n+/)
      .map((s: string) => s.trim())
      .filter(Boolean);
    try {
      await apiFetch(`/feature-sets/${encodeURIComponent(selectedId)}`, {
        method: "PUT",
        body: JSON.stringify({
          description: v.description,
          kind: v.kind,
          specs,
          default_lookback_days: Number(v.default_lookback_days || 60),
          tags: v.tags || [],
          notes: "edit via workbench",
        }),
      });
      message.success("Saved");
      void detail.refetch();
      void versions.refetch();
      void list.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function remove() {
    if (!selectedId) return;
    modal.confirm({
      title: "Archive this feature set?",
      content: "Archived feature sets are hidden but can still be referenced from existing runs.",
      okText: "Archive",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await apiFetch(`/feature-sets/${encodeURIComponent(selectedId)}`, {
            method: "DELETE",
          });
          message.success("Archived");
          setSelectedId(null);
          void list.refetch();
        } catch (err) {
          message.error((err as Error).message);
        }
      },
    });
  }

  async function create() {
    const v = await createForm.validateFields();
    const specs = String(v.specs ?? "")
      .split(/\n+/)
      .map((s: string) => s.trim())
      .filter(Boolean);
    try {
      const created = (await apiFetch<FeatureSetSummary>("/feature-sets", {
        method: "POST",
        body: JSON.stringify({
          name: v.name,
          description: v.description,
          kind: v.kind || "indicator",
          specs,
          default_lookback_days: Number(v.default_lookback_days || 60),
          tags: v.tags || [],
        }),
      }));
      message.success(`Created ${created.name}`);
      setCreateOpen(false);
      createForm.resetFields();
      setSelectedId(created.id);
      void list.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  function appendSpec(spec: string) {
    const current = String(form.getFieldValue("specs") ?? "");
    const next = current ? `${current}\n${spec}` : spec;
    form.setFieldValue("specs", next);
    message.success(`Added ${spec}`);
  }

  async function runPreview() {
    if (!selectedId) return;
    setPreviewLoading(true);
    try {
      const resp = await apiFetch<FeatureSetPreviewResp>(
        `/feature-sets/${encodeURIComponent(selectedId)}/preview`,
        {
          method: "POST",
          body: JSON.stringify({
            symbols: previewSymbols,
            start: previewStart,
            end: previewEnd,
            rows: 50,
          }),
        },
      );
      setPreview(resp);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <PageContainer
      title="Feature Sets"
      subtitle="Named, versioned bundles of indicator / model-prediction specs."
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          New feature set
        </Button>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="All feature sets" size="small">
            {items.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="None yet." />
            ) : (
              <Space direction="vertical" style={{ width: "100%" }}>
                {items.map((it) => (
                  <Button
                    key={it.id}
                    block
                    type={selectedId === it.id ? "primary" : "default"}
                    onClick={() => setSelectedId(it.id)}
                    style={{ textAlign: "left" }}
                  >
                    <Space>
                      <Text strong>{it.name}</Text>
                      <Tag color="blue">v{it.version}</Tag>
                      <Tag>{it.kind}</Tag>
                    </Space>
                  </Button>
                ))}
              </Space>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          {!selected ? (
            <Card>
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="Pick a feature set on the left, or create a new one."
              />
            </Card>
          ) : (
            <>
              <Card
                size="small"
                title={
                  <Space>
                    <Text strong>{selected.name}</Text>
                    <Tag color="blue">v{selected.version}</Tag>
                    <Tag>{selected.kind}</Tag>
                  </Space>
                }
                extra={
                  <Space>
                    <Button onClick={save} type="primary">
                      Save
                    </Button>
                    <Button danger icon={<DeleteOutlined />} onClick={remove} />
                  </Space>
                }
              >
                <Form layout="vertical" form={form} initialValues={formInitial}>
                  <Form.Item label="Description" name="description">
                    <Input.TextArea rows={2} />
                  </Form.Item>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item label="Kind" name="kind" initialValue="indicator">
                        <Select options={KIND_OPTIONS} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label="Default lookback (days)" name="default_lookback_days">
                        <InputNumber min={1} max={3000} style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Form.Item label="Tags" name="tags">
                    <Select mode="tags" tokenSeparators={[","]} />
                  </Form.Item>
                  <Form.Item
                    label={
                      <Space>
                        <Text>Specs (one per line)</Text>
                        <Button size="small" icon={<ExperimentOutlined />} onClick={() => setPicker("indicators")}>
                          Pick indicator
                        </Button>
                        <Button size="small" onClick={() => setPicker("candidates")}>
                          Pick feed field
                        </Button>
                      </Space>
                    }
                    name="specs"
                    tooltip="IndicatorZoo specs e.g. SMA:20, RSI:14, MACD, ModelPred:deployment_id=...,column_name=mp1"
                  >
                    <Input.TextArea rows={8} style={{ fontFamily: "monospace" }} />
                  </Form.Item>
                </Form>
              </Card>

              <Card title="Preview" size="small" style={{ marginTop: 16 }}>
                <Form layout="inline" style={{ marginBottom: 8 }}>
                  <Form.Item label="Symbols">
                    <Select
                      mode="tags"
                      tokenSeparators={[",", " "]}
                      value={previewSymbols}
                      onChange={(v) => setPreviewSymbols(v as string[])}
                      style={{ minWidth: 220 }}
                    />
                  </Form.Item>
                  <Form.Item label="Start">
                    <Input value={previewStart} onChange={(e) => setPreviewStart(e.target.value)} />
                  </Form.Item>
                  <Form.Item label="End">
                    <Input value={previewEnd} onChange={(e) => setPreviewEnd(e.target.value)} />
                  </Form.Item>
                  <Button
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    loading={previewLoading}
                    onClick={runPreview}
                  >
                    Materialize
                  </Button>
                </Form>
                {preview?.warning ? (
                  <Alert type="warning" showIcon message={preview.warning} style={{ marginBottom: 8 }} />
                ) : null}
                {preview && preview.rows.length > 0 ? (
                  <Table
                    size="small"
                    rowKey={(_, idx) => String(idx)}
                    dataSource={preview.rows.slice(0, 20) as Array<Record<string, unknown>>}
                    pagination={false}
                    scroll={{ x: true }}
                    columns={preview.columns.map((c) => ({
                      title: c,
                      dataIndex: c,
                      key: c,
                      render: (v: unknown) => {
                        if (typeof v === "number") {
                          return Number.isFinite(v) ? v.toFixed(4) : "—";
                        }
                        return String(v ?? "—");
                      },
                    }))}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Run materialize to preview." />
                )}
              </Card>

              <Tabs
                style={{ marginTop: 16 }}
                items={[
                  {
                    key: "versions",
                    label: "Versions",
                    children: (
                      <Table
                        size="small"
                        rowKey="id"
                        dataSource={versions.data ?? []}
                        pagination={{ pageSize: 10 }}
                        columns={[
                          { title: "Version", dataIndex: "version", width: 80 },
                          { title: "Notes", dataIndex: "notes" },
                          { title: "By", dataIndex: "created_by", width: 120 },
                          {
                            title: "Specs",
                            dataIndex: "specs",
                            render: (s: string[] | undefined) =>
                              (s ?? []).map((x) => (
                                <Tag key={x} style={{ margin: 2 }}>
                                  {x}
                                </Tag>
                              )),
                          },
                          { title: "Created", dataIndex: "created_at", width: 180 },
                        ]}
                      />
                    ),
                  },
                  {
                    key: "usages",
                    label: "Usages",
                    children: (
                      <Table
                        size="small"
                        rowKey="id"
                        dataSource={usages.data ?? []}
                        pagination={{ pageSize: 10 }}
                        columns={[
                          { title: "Consumer", dataIndex: "consumer_kind", width: 120 },
                          { title: "Consumer ID", dataIndex: "consumer_id" },
                          { title: "Version", dataIndex: "version", width: 80 },
                          { title: "Created", dataIndex: "created_at", width: 180 },
                        ]}
                      />
                    ),
                  },
                  {
                    key: "details",
                    label: "Details",
                    children: (
                      <Descriptions size="small" column={1}>
                        <Descriptions.Item label="ID">{selected.id}</Descriptions.Item>
                        <Descriptions.Item label="Name">{selected.name}</Descriptions.Item>
                        <Descriptions.Item label="Status">{selected.status}</Descriptions.Item>
                        <Descriptions.Item label="Created at">{selected.created_at}</Descriptions.Item>
                        <Descriptions.Item label="Updated at">{selected.updated_at}</Descriptions.Item>
                      </Descriptions>
                    ),
                  },
                ]}
              />
            </>
          )}
        </Col>
      </Row>

      <Drawer
        open={picker === "indicators"}
        title="Indicator catalog"
        width={420}
        onClose={() => setPicker(null)}
      >
        <List
          loading={indicatorCatalog.isFetching}
          dataSource={(indicatorCatalog.data?.groups ?? []).flatMap((g) => g.indicators)}
          pagination={{ pageSize: 20 }}
          renderItem={(ind) => {
            const period = ind.params.find((p) => p.name === "timeperiod")?.default;
            const spec = period ? `${ind.name}:${period}` : ind.name;
            return (
              <List.Item
                actions={[
                  <Button key="add" size="small" onClick={() => appendSpec(spec)}>
                    Insert
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>{ind.name}</Text>
                      <Tag>{ind.group}</Tag>
                    </Space>
                  }
                  description={ind.description}
                />
              </List.Item>
            );
          }}
        />
      </Drawer>
      <Drawer
        open={picker === "candidates"}
        title="Feed feature candidates"
        width={420}
        onClose={() => setPicker(null)}
      >
        <List
          loading={featureCandidates.isFetching}
          dataSource={featureCandidates.data?.candidates ?? []}
          pagination={{ pageSize: 25 }}
          renderItem={(cand) => {
            const spec = `Field:${cand.source}.${cand.domain}.${cand.field}`;
            return (
              <List.Item
                actions={[
                  <Button key="add" size="small" onClick={() => appendSpec(spec)}>
                    Insert
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>{cand.field}</Text>
                      <Tag color="blue">{cand.source}</Tag>
                      <Tag color="cyan">{cand.domain}</Tag>
                    </Space>
                  }
                  description={cand.description}
                />
              </List.Item>
            );
          }}
        />
      </Drawer>

      <Modal
        title="New feature set"
        open={createOpen}
        onOk={create}
        onCancel={() => setCreateOpen(false)}
        okText="Create"
      >
        <Form layout="vertical" form={createForm}>
          <Form.Item
            name="name"
            label="Name"
            rules={[{ required: true, message: "Name is required" }]}
          >
            <Input placeholder="e.g. tech_panel_v1" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="kind" label="Kind" initialValue="indicator">
            <Select options={KIND_OPTIONS} />
          </Form.Item>
          <Form.Item name="default_lookback_days" label="Default lookback (days)" initialValue={60}>
            <InputNumber min={1} max={3000} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="tags" label="Tags">
            <Select mode="tags" tokenSeparators={[","]} />
          </Form.Item>
          <Form.Item
            name="specs"
            label="Specs (one per line)"
            tooltip="IndicatorZoo specs e.g. SMA:20, RSI:14, MACD"
          >
            <Input.TextArea rows={6} style={{ fontFamily: "monospace" }} />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
}

export function FeatureSetSummaryCard({ summary }: { summary: FeatureSetSummary }) {
  return (
    <Card size="small">
      <Title level={5} style={{ marginTop: 0 }}>
        {summary.name}
      </Title>
      <Paragraph type="secondary">{summary.description ?? "—"}</Paragraph>
      <Space wrap>
        {summary.specs.slice(0, 8).map((s) => (
          <Tag key={s}>{s}</Tag>
        ))}
        {summary.specs.length > 8 ? <Tag>+{summary.specs.length - 8}</Tag> : null}
      </Space>
    </Card>
  );
}
