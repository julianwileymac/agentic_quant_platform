"use client";

import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";

const { Text, Paragraph } = Typography;

interface FieldDoc {
  id?: number | null;
  name: string;
  type?: string | null;
  required?: boolean;
  description?: string | null;
  pii?: boolean;
}

interface SnapshotEntry {
  snapshot_id: number;
  parent_snapshot_id?: number | null;
  operation?: string | null;
  timestamp_ms: number;
  summary?: Record<string, string>;
}

interface TableDetail {
  iceberg_identifier: string;
  namespace: string;
  name: string;
  description?: string | null;
  domain?: string | null;
  tags?: string[];
  load_mode: string;
  source_uri?: string | null;
  row_count?: number | null;
  file_count?: number | null;
  truncated: boolean;
  has_annotation: boolean;
  catalog_id?: string | null;
  location?: string | null;
  fields: FieldDoc[];
  partition_spec: { name: string; transform: string }[];
  snapshots: SnapshotEntry[];
  llm_annotations: Record<string, unknown>;
  sample_rows: Record<string, unknown>[];
}

interface QueryResult {
  rows: Record<string, unknown>[];
  count: number;
  columns: string[];
}

interface AnnotateResponse {
  task_id: string;
  stream_url?: string | null;
}

interface GroupingSuggestion {
  group_name: string;
  members: string[];
  reason?: string | null;
  score?: number;
}

interface CatalogTableDetailProps {
  namespace: string;
  name: string;
}

export function CatalogTableDetail({ namespace, name }: CatalogTableDetailProps) {
  const router = useRouter();
  const { message, modal } = App.useApp();
  const [activeTab, setActiveTab] = useState<string>("schema");

  const detail = useApiQuery<TableDetail>({
    queryKey: ["dataset", namespace, name],
    path: `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`,
    query: { sample_rows: 10 },
    staleTime: 5_000,
  });

  const [editingDescription, setEditingDescription] = useState(false);
  const [descDraft, setDescDraft] = useState("");
  const [tagsDraft, setTagsDraft] = useState<string[]>([]);
  const [columnDraft, setColumnDraft] = useState<Record<string, { description: string; pii: boolean }>>({});

  useEffect(() => {
    if (detail.data) {
      setDescDraft(detail.data.description ?? "");
      setTagsDraft(detail.data.tags ?? []);
      const cols: Record<string, { description: string; pii: boolean }> = {};
      for (const f of detail.data.fields) {
        cols[f.name] = { description: f.description ?? "", pii: Boolean(f.pii) };
      }
      setColumnDraft(cols);
    }
  }, [detail.data]);

  // SQL preview
  const [sql, setSql] = useState("SELECT * FROM " + name + " LIMIT 100");
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [queryRunning, setQueryRunning] = useState(false);
  const [queryLimit, setQueryLimit] = useState(200);
  const [xColumn, setXColumn] = useState<string | undefined>();
  const [yColumn, setYColumn] = useState<string | undefined>();

  // Annotation re-run
  const [annotateTaskId, setAnnotateTaskId] = useState<string | null>(null);
  const annotateStream = useChatStream(annotateTaskId);
  const [groupStrategy, setGroupStrategy] = useState<"heuristic" | "llm">("heuristic");
  const [groupSuggestions, setGroupSuggestions] = useState<GroupingSuggestion[]>([]);
  const [groupingRunning, setGroupingRunning] = useState(false);
  const [manualGroupName, setManualGroupName] = useState(`${namespace}.${name}`);
  const [manualMembers, setManualMembers] = useState(`${namespace}.${name}`);

  useEffect(() => {
    if (annotateStream.done && annotateTaskId) {
      message.success("Annotation refreshed");
      detail.refetch();
      setAnnotateTaskId(null);
    }
    if (annotateStream.error) {
      message.error(`Annotation failed: ${annotateStream.error}`);
    }
  }, [annotateStream.done, annotateStream.error, annotateTaskId, message, detail]);

  useEffect(() => {
    setManualGroupName(`${namespace}.${name}`);
    setManualMembers(`${namespace}.${name}`);
  }, [namespace, name]);

  const sampleColumns = useMemo(() => {
    const rows = detail.data?.sample_rows ?? [];
    if (rows.length === 0) return [] as { title: string; dataIndex: string; key: string }[];
    const keys = Object.keys(rows[0] ?? {});
    return keys.slice(0, 32).map((k) => ({
      title: k,
      dataIndex: k,
      key: k,
      ellipsis: true,
      render: (v: unknown) => {
        if (v === null || v === undefined) return <Text type="secondary">—</Text>;
        const s = typeof v === "string" ? v : JSON.stringify(v);
        return <Text style={{ fontFamily: "monospace", fontSize: 12 }}>{s}</Text>;
      },
    }));
  }, [detail.data]);

  async function persistEdits() {
    if (!detail.data) return;
    const payload = {
      description: descDraft,
      tags: tagsDraft,
      column_docs: Object.entries(columnDraft).map(([cname, doc]) => ({
        name: cname,
        description: doc.description,
        pii: doc.pii,
      })),
    };
    try {
      await apiFetch(
        `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
      message.success("Catalog updated");
      setEditingDescription(false);
      detail.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function runQuery() {
    setQueryRunning(true);
    try {
      const res = await apiFetch<QueryResult>(
        `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/query`,
        { method: "POST", body: JSON.stringify({ sql, limit: queryLimit }) },
      );
      setQueryResult(res);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setQueryRunning(false);
    }
  }

  const queryColumns = queryResult?.columns ?? [];
  const numericColumns = useMemo(() => {
    if (!queryResult) return [] as string[];
    return queryResult.columns.filter((c) =>
      queryResult.rows.some((r) => typeof r[c] === "number" && Number.isFinite(r[c])),
    );
  }, [queryResult]);

  useEffect(() => {
    if (!queryResult) return;
    setXColumn((current) => current && queryColumns.includes(current) ? current : queryColumns[0]);
    setYColumn((current) =>
      current && numericColumns.includes(current) ? current : numericColumns[0],
    );
  }, [queryResult, queryColumns, numericColumns]);

  const chartRows = useMemo(() => {
    if (!queryResult || !xColumn || !yColumn) return [] as { label: string; value: number }[];
    return queryResult.rows
      .map((row, idx) => {
        const rawValue = row[yColumn];
        const value = typeof rawValue === "number" ? rawValue : Number(rawValue);
        return {
          label: String(row[xColumn] ?? `Row ${idx + 1}`),
          value: Number.isFinite(value) ? value : 0,
        };
      })
      .slice(0, 25);
  }, [queryResult, xColumn, yColumn]);

  const maxChartValue = Math.max(...chartRows.map((r) => Math.abs(r.value)), 1);
  const pythonSnippet = useMemo(() => {
    const url = `http://localhost:8000/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/query`;
    return [
      "import pandas as pd",
      "import requests",
      "",
      `url = ${JSON.stringify(url)}`,
      `payload = {"sql": ${JSON.stringify(sql)}, "limit": ${queryLimit}}`,
      "resp = requests.post(url, json=payload, timeout=120)",
      "resp.raise_for_status()",
      "df = pd.DataFrame(resp.json()[\"rows\"])",
      "df.head()",
    ].join("\n");
  }, [namespace, name, sql, queryLimit]);

  async function reannotate() {
    try {
      const res = await apiFetch<AnnotateResponse>(
        `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/annotate`,
        { method: "POST", body: JSON.stringify({ sample_rows: 25 }) },
      );
      setAnnotateTaskId(res.task_id);
      message.info("Annotation queued; streaming progress…");
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function proposeGrouping() {
    setGroupingRunning(true);
    try {
      const res = await apiFetch<{ groups?: GroupingSuggestion[] }>("/datasets/grouping/propose", {
        method: "POST",
        body: JSON.stringify({
          namespace,
          strategy: groupStrategy,
          min_group_size: 2,
        }),
      });
      setGroupSuggestions(res.groups ?? []);
      message.success(`Loaded ${res.groups?.length ?? 0} grouping proposals`);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setGroupingRunning(false);
    }
  }

  async function applyGrouping(group: GroupingSuggestion) {
    try {
      await apiFetch("/datasets/grouping/apply", {
        method: "POST",
        body: JSON.stringify({
          groups: [group],
        }),
      });
      message.success(`Applied group ${group.group_name}`);
      detail.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function applyManualGrouping() {
    const members = manualMembers
      .split(/[,\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!manualGroupName || members.length === 0) {
      message.warning("Enter group name and at least one member identifier");
      return;
    }
    await applyGrouping({
      group_name: manualGroupName.trim(),
      members,
      reason: "manual",
      score: 1.0,
    });
  }

  function confirmDelete() {
    modal.confirm({
      title: "Drop this Iceberg table?",
      content: `This permanently drops ${detail.data?.iceberg_identifier} and removes its catalog row. Source files are unaffected.`,
      okType: "danger",
      okText: "Drop",
      onOk: async () => {
        try {
          await apiFetch(
            `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`,
            { method: "DELETE" },
          );
          message.success("Dropped");
          router.push("/data/catalog");
        } catch (err) {
          message.error((err as Error).message);
        }
      },
    });
  }

  if (detail.error) {
    return (
      <PageContainer title={`${namespace}.${name}`}>
        <Alert
          type="error"
          showIcon
          message="Could not load table detail"
          description={(detail.error as Error).message}
        />
      </PageContainer>
    );
  }

  const data = detail.data;

  return (
    <PageContainer
      title={data ? `${data.namespace}.${data.name}` : `${namespace}.${name}`}
      subtitle={
        data?.description ?? "No description yet — annotate from the LLM panel below."
      }
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => detail.refetch()}>
            Refresh
          </Button>
          <Button
            icon={<ThunderboltOutlined />}
            onClick={reannotate}
            loading={annotateStream.status === "open"}
          >
            Re-annotate
          </Button>
          <Button danger icon={<DeleteOutlined />} onClick={confirmDelete}>
            Drop
          </Button>
        </Space>
      }
    >
      {data?.truncated ? (
        <Alert
          type="warning"
          showIcon
          message="Truncated during ingest"
          description="One or more files were skipped because the row/file caps were hit. Re-run with higher caps or a smaller archive to ingest the full corpus."
          style={{ marginBottom: 12 }}
        />
      ) : null}

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: "schema",
            label: "Schema",
            children: (
              <Card size="small">
                {data?.fields?.length ? (
                  <List
                    size="small"
                    dataSource={data.fields}
                    renderItem={(f) => (
                      <List.Item>
                        <Space direction="vertical" size={0} style={{ width: "100%" }}>
                          <Space>
                            <Text strong>{f.name}</Text>
                            <Tag>{f.type ?? "?"}</Tag>
                            {columnDraft[f.name]?.pii ? <Tag color="red">PII</Tag> : null}
                          </Space>
                          <Input.TextArea
                            autoSize
                            placeholder="Add a description (saved on Save)"
                            value={columnDraft[f.name]?.description ?? ""}
                            onChange={(e) =>
                              setColumnDraft((prev) => ({
                                ...prev,
                                [f.name]: {
                                  description: e.target.value,
                                  pii: prev[f.name]?.pii ?? false,
                                },
                              }))
                            }
                          />
                          <Space>
                            <Button
                              size="small"
                              type={columnDraft[f.name]?.pii ? "primary" : "default"}
                              danger={columnDraft[f.name]?.pii}
                              onClick={() =>
                                setColumnDraft((prev) => ({
                                  ...prev,
                                  [f.name]: {
                                    description: prev[f.name]?.description ?? "",
                                    pii: !(prev[f.name]?.pii ?? false),
                                  },
                                }))
                              }
                            >
                              {columnDraft[f.name]?.pii ? "PII flag set" : "Mark as PII"}
                            </Button>
                          </Space>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description="No schema available yet" />
                )}
                <Space style={{ marginTop: 16 }}>
                  <Button type="primary" icon={<EditOutlined />} onClick={persistEdits}>
                    Save schema docs
                  </Button>
                </Space>
              </Card>
            ),
          },
          {
            key: "sample",
            label: "Sample",
            children: (
              <Card size="small">
                {data?.sample_rows?.length ? (
                  <Table
                    size="small"
                    rowKey={(_row, idx) => `r-${idx ?? 0}`}
                    columns={sampleColumns}
                    dataSource={data.sample_rows}
                    pagination={{ pageSize: 25 }}
                    scroll={{ x: "max-content" }}
                  />
                ) : (
                  <Empty description="No rows ingested yet" />
                )}
              </Card>
            ),
          },
          {
            key: "query",
            label: "Query",
            children: (
              <Card size="small">
                <Form layout="vertical">
                  <Form.Item label="DuckDB SQL (the table is registered as a view named after the Iceberg table)">
                    <Input.TextArea
                      autoSize={{ minRows: 4 }}
                      value={sql}
                      onChange={(e) => setSql(e.target.value)}
                    />
                  </Form.Item>
                  <Space>
                    <Form.Item label="Result limit" style={{ marginBottom: 0 }}>
                      <InputNumber
                        min={1}
                        max={10_000}
                        value={queryLimit}
                        onChange={(value) => setQueryLimit(Number(value ?? 200))}
                      />
                    </Form.Item>
                    <Button
                      type="primary"
                      icon={<PlayCircleOutlined />}
                      loading={queryRunning}
                      onClick={runQuery}
                    >
                      Run query
                    </Button>
                  </Space>
                </Form>
                <div style={{ marginTop: 16 }}>
                  {queryResult ? (
                    <Table
                      size="small"
                      rowKey={(_row, idx) => `q-${idx ?? 0}`}
                      columns={queryResult.columns.map((c) => ({
                        title: c,
                        dataIndex: c,
                        key: c,
                        ellipsis: true,
                      }))}
                      dataSource={queryResult.rows}
                      pagination={{ pageSize: 25 }}
                      scroll={{ x: "max-content" }}
                    />
                  ) : (
                    <Empty description="Run a query to see results" />
                  )}
                </div>
                {queryResult ? (
                  <Card
                    size="small"
                    title="Interactive Visualization"
                    style={{ marginTop: 16 }}
                  >
                    {numericColumns.length ? (
                      <Space direction="vertical" style={{ width: "100%" }}>
                        <Space wrap>
                          <Select
                            style={{ width: 220 }}
                            value={xColumn}
                            options={queryColumns.map((c) => ({ label: c, value: c }))}
                            onChange={setXColumn}
                            placeholder="X column"
                          />
                          <Select
                            style={{ width: 220 }}
                            value={yColumn}
                            options={numericColumns.map((c) => ({ label: c, value: c }))}
                            onChange={setYColumn}
                            placeholder="Numeric Y column"
                          />
                        </Space>
                        <Space direction="vertical" style={{ width: "100%" }}>
                          {chartRows.map((row, idx) => (
                            <div key={`${row.label}-${idx}`} style={{ width: "100%" }}>
                              <Space style={{ width: "100%", alignItems: "center" }}>
                                <Text
                                  style={{
                                    width: 220,
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    whiteSpace: "nowrap",
                                  }}
                                  title={row.label}
                                >
                                  {row.label}
                                </Text>
                                <div
                                  style={{
                                    height: 20,
                                    minWidth: 2,
                                    width: `${Math.max(2, (Math.abs(row.value) / maxChartValue) * 420)}px`,
                                    background: row.value >= 0 ? "#1677ff" : "#ff4d4f",
                                    borderRadius: 4,
                                  }}
                                />
                                <Text code>{row.value.toLocaleString()}</Text>
                              </Space>
                            </div>
                          ))}
                        </Space>
                      </Space>
                    ) : (
                      <Empty description="Run a query with at least one numeric result column to chart it" />
                    )}
                  </Card>
                ) : null}
                <Card size="small" title="Python Analysis" style={{ marginTop: 16 }}>
                  <Paragraph>
                    Run the same catalog query from a notebook or Python shell and continue with pandas.
                  </Paragraph>
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      margin: 0,
                      padding: 12,
                      borderRadius: 8,
                      background: "#0b1020",
                      color: "#d6e4ff",
                      overflowX: "auto",
                    }}
                  >
                    {pythonSnippet}
                  </pre>
                </Card>
              </Card>
            ),
          },
          {
            key: "annotations",
            label: "Annotations",
            children: (
              <Card size="small">
                <Form layout="vertical">
                  <Form.Item label="Description">
                    <Input.TextArea
                      autoSize={{ minRows: 3 }}
                      value={descDraft}
                      onChange={(e) => setDescDraft(e.target.value)}
                    />
                  </Form.Item>
                  <Form.Item label="Tags">
                    <Select
                      mode="tags"
                      value={tagsDraft}
                      onChange={(values: string[]) => setTagsDraft(values)}
                      style={{ width: "100%" }}
                      placeholder="Add or remove tags"
                    />
                  </Form.Item>
                  <Space>
                    <Button type="primary" onClick={persistEdits}>
                      Save annotations
                    </Button>
                    <Button onClick={reannotate}>Re-run LLM annotation</Button>
                  </Space>
                </Form>
                {data?.llm_annotations &&
                Object.keys(data.llm_annotations).length > 0 ? (
                  <Card size="small" style={{ marginTop: 16 }} title="Latest LLM payload">
                    <Paragraph style={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: 12 }}>
                      {JSON.stringify(data.llm_annotations, null, 2)}
                    </Paragraph>
                  </Card>
                ) : null}
              </Card>
            ),
          },
          {
            key: "grouping",
            label: "Grouping",
            children: (
              <Card size="small">
                <Paragraph>
                  Consolidate fragmented table loads by tagging logical groups. Proposals can be
                  heuristic or LLM-assisted.
                </Paragraph>
                <Space wrap style={{ marginBottom: 12 }}>
                  <Select
                    value={groupStrategy}
                    options={[
                      { value: "heuristic", label: "Heuristic" },
                      { value: "llm", label: "LLM-assisted" },
                    ]}
                    onChange={(v) => setGroupStrategy(v as "heuristic" | "llm")}
                    style={{ width: 180 }}
                  />
                  <Button loading={groupingRunning} onClick={proposeGrouping}>
                    Suggest groups for namespace
                  </Button>
                </Space>
                <List
                  size="small"
                  bordered
                  dataSource={groupSuggestions.filter((g) =>
                    g.members.some((m) => m === `${namespace}.${name}`),
                  )}
                  locale={{ emptyText: "No suggestions yet for this table." }}
                  renderItem={(g) => (
                    <List.Item
                      actions={[
                        <Button key="apply" type="link" onClick={() => applyGrouping(g)}>
                          Apply
                        </Button>,
                      ]}
                    >
                      <Space direction="vertical" size={2}>
                        <Text strong>{g.group_name}</Text>
                        <Text type="secondary">{g.reason || "suggested group"}</Text>
                        <Text code>{g.members.join(", ")}</Text>
                      </Space>
                    </List.Item>
                  )}
                />
                <Divider />
                <Form layout="vertical">
                  <Form.Item label="Manual group name">
                    <Input value={manualGroupName} onChange={(e) => setManualGroupName(e.target.value)} />
                  </Form.Item>
                  <Form.Item label="Members (full identifiers, comma or newline separated)">
                    <Input.TextArea
                      autoSize={{ minRows: 3 }}
                      value={manualMembers}
                      onChange={(e) => setManualMembers(e.target.value)}
                    />
                  </Form.Item>
                  <Button type="primary" onClick={applyManualGrouping}>
                    Apply manual grouping
                  </Button>
                </Form>
              </Card>
            ),
          },
          {
            key: "lineage",
            label: "Lineage",
            children: (
              <Card size="small">
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="Iceberg identifier">
                    {data?.iceberg_identifier}
                  </Descriptions.Item>
                  <Descriptions.Item label="Location">
                    {data?.location ?? "—"}
                  </Descriptions.Item>
                  <Descriptions.Item label="Source URI">
                    {data?.source_uri ?? "—"}
                  </Descriptions.Item>
                  <Descriptions.Item label="Load mode">
                    <Tag>{data?.load_mode ?? "—"}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="Partition spec">
                    {data?.partition_spec?.length
                      ? data.partition_spec.map((p) => `${p.name} (${p.transform})`).join(", ")
                      : "(unpartitioned)"}
                  </Descriptions.Item>
                </Descriptions>
                <Card
                  size="small"
                  style={{ marginTop: 16 }}
                  title={`Snapshots (${data?.snapshots?.length ?? 0})`}
                >
                  {data?.snapshots?.length ? (
                    <List
                      size="small"
                      dataSource={data.snapshots}
                      renderItem={(s) => (
                        <List.Item>
                          <Space direction="vertical" size={0}>
                            <Text strong>#{s.snapshot_id}</Text>
                            <Text type="secondary">
                              {new Date(s.timestamp_ms).toISOString()} · {s.operation ?? "unknown"}
                            </Text>
                            <Text style={{ fontFamily: "monospace", fontSize: 12 }}>
                              {JSON.stringify(s.summary ?? {})}
                            </Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty description="No snapshots" />
                  )}
                </Card>
              </Card>
            ),
          },
        ]}
      />

      <Modal
        title="Edit description"
        open={editingDescription}
        onOk={persistEdits}
        onCancel={() => setEditingDescription(false)}
      >
        <Input.TextArea
          autoSize={{ minRows: 4 }}
          value={descDraft}
          onChange={(e) => setDescDraft(e.target.value)}
        />
      </Modal>
    </PageContainer>
  );
}
