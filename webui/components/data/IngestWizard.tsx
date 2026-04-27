"use client";

import {
  CloudUploadOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Space,
  Steps,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws";

const { Text, Paragraph } = Typography;

interface DiscoveredMember {
  path: string;
  archive_path?: string | null;
  format: string;
  delimiter?: string | null;
  size_bytes: number;
}

interface DiscoveredDataset {
  family: string;
  file_count: number;
  format: string;
  delimiter?: string | null;
  total_bytes: number;
  sample_columns: string[];
  notes: string[];
  members: DiscoveredMember[];
}

interface DiscoveryResponse {
  source_path: string;
  datasets: DiscoveredDataset[];
  extras: { path: string; archive_path?: string | null; size_bytes: number }[];
}

interface IngestResponse {
  task_id: string;
  stream_url?: string | null;
}

function bytesToHuman(bytes: number): string {
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)} ${u[i]}`;
}

export function IngestWizard() {
  const { message } = App.useApp();
  const router = useRouter();
  const [step, setStep] = useState(0);

  const [path, setPath] = useState("");
  const [namespace, setNamespace] = useState("aqp");
  const [tablePrefix, setTablePrefix] = useState("");
  const [annotate, setAnnotate] = useState(true);
  const [maxRows, setMaxRows] = useState<number | null>(5_000_000);
  const [maxFiles, setMaxFiles] = useState<number | null>(2000);

  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null);
  const [discovering, setDiscovering] = useState(false);

  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  async function runDiscovery() {
    if (!path.trim()) {
      message.warning("Enter a path first");
      return;
    }
    setDiscovering(true);
    try {
      const res = await apiFetch<DiscoveryResponse>("/pipelines/discovery/preview", {
        query: { path: path.trim() },
      });
      setDiscovery(res);
      message.success(`Discovered ${res.datasets.length} dataset(s)`);
      setStep(1);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setDiscovering(false);
    }
  }

  async function submit() {
    try {
      const res = await apiFetch<IngestResponse>("/pipelines/ingest", {
        method: "POST",
        body: JSON.stringify({
          path: path.trim(),
          namespace: namespace.trim() || null,
          table_prefix: tablePrefix.trim() || null,
          annotate,
          max_rows_per_dataset: maxRows ?? null,
          max_files_per_dataset: maxFiles ?? null,
        }),
      });
      setTaskId(res.task_id);
      setStep(2);
      message.success(`Ingest queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Data Ingest"
      subtitle="Materialize files, folders, or zipped archives into Iceberg-managed tables — with optional LLM annotations."
    >
      <Card>
        <Steps
          current={step}
          items={[
            { title: "Source", icon: <FolderOpenOutlined /> },
            { title: "Preview", icon: <EyeOutlined /> },
            { title: "Run", icon: <CloudUploadOutlined /> },
          ]}
        />

        <div style={{ marginTop: 24 }}>
          {step === 0 ? (
            <Form layout="vertical" style={{ maxWidth: 720 }}>
              <Form.Item
                label="Source path"
                required
                tooltip="Absolute path on the API host. Folders, single files, and ZIP archives are all supported."
              >
                <Input
                  prefix={<FolderOpenOutlined />}
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  placeholder="C:/Users/.../Downloads/cfpb"
                />
              </Form.Item>
              <Form.Item label="Iceberg namespace">
                <Input value={namespace} onChange={(e) => setNamespace(e.target.value)} />
              </Form.Item>
              <Form.Item label="Table name prefix (optional)">
                <Input
                  value={tablePrefix}
                  onChange={(e) => setTablePrefix(e.target.value)}
                  placeholder="e.g. cfpb"
                />
              </Form.Item>
              <Form.Item label="Run LLM annotation after ingest" valuePropName="checked">
                <Switch checked={annotate} onChange={(v) => setAnnotate(v)} />
              </Form.Item>
              <Form.Item label="Row cap per dataset">
                <InputNumber
                  min={1000}
                  step={1000}
                  value={maxRows ?? undefined}
                  onChange={(v) => setMaxRows(v ?? null)}
                  style={{ width: "100%" }}
                />
              </Form.Item>
              <Form.Item label="File cap per dataset">
                <InputNumber
                  min={1}
                  step={1}
                  value={maxFiles ?? undefined}
                  onChange={(v) => setMaxFiles(v ?? null)}
                  style={{ width: "100%" }}
                />
              </Form.Item>
              <Space>
                <Button
                  type="primary"
                  icon={<EyeOutlined />}
                  onClick={runDiscovery}
                  loading={discovering}
                >
                  Discover datasets
                </Button>
              </Space>
            </Form>
          ) : null}

          {step === 1 ? (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Alert
                type="info"
                showIcon
                message={`Found ${discovery?.datasets.length ?? 0} logical dataset(s) under ${
                  discovery?.source_path ?? path
                }`}
                description={
                  discovery?.extras?.length
                    ? `${discovery.extras.length} non-tabular asset(s) will be skipped at materialize time.`
                    : "All members are tabular and will be materialized into Iceberg."
                }
              />
              {discovery?.datasets.length ? (
                <Table
                  size="small"
                  rowKey="family"
                  dataSource={discovery.datasets}
                  pagination={{ pageSize: 10 }}
                  columns={[
                    { title: "Table", dataIndex: "family", key: "family", render: (v: string) => <Text strong>{v}</Text> },
                    {
                      title: "Format",
                      dataIndex: "format",
                      key: "format",
                      render: (v: string, row: DiscoveredDataset) => (
                        <Space>
                          <Tag>{v}</Tag>
                          {row.delimiter ? <Tag color="geekblue">delim={row.delimiter}</Tag> : null}
                        </Space>
                      ),
                    },
                    { title: "Files", dataIndex: "file_count", key: "files" },
                    {
                      title: "Size",
                      dataIndex: "total_bytes",
                      key: "size",
                      render: (v: number) => bytesToHuman(v),
                    },
                    {
                      title: "Sample columns",
                      dataIndex: "sample_columns",
                      key: "sample_columns",
                      render: (cols: string[]) => (
                        <Space wrap>
                          {cols.slice(0, 6).map((c) => (
                            <Tag key={c}>{c}</Tag>
                          ))}
                          {cols.length > 6 ? <Text type="secondary">+{cols.length - 6} more</Text> : null}
                        </Space>
                      ),
                    },
                  ]}
                />
              ) : (
                <Empty description="No tabular datasets detected" />
              )}
              <Space>
                <Button onClick={() => setStep(0)}>Back</Button>
                <Button
                  type="primary"
                  icon={<CloudUploadOutlined />}
                  onClick={submit}
                  disabled={!discovery?.datasets.length}
                >
                  Materialize into Iceberg
                </Button>
              </Space>
            </Space>
          ) : null}

          {step === 2 ? (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Alert
                type="info"
                showIcon
                message={`Task ${taskId ?? ""}`}
                description={
                  stream.status === "open"
                    ? "Streaming progress…"
                    : stream.done
                      ? "Done. Browse the catalog to see results."
                      : `WS status: ${stream.status}`
                }
              />
              <Card size="small" title="Live progress">
                {stream.events.length === 0 ? (
                  <Empty description="Waiting for events" />
                ) : (
                  <List
                    size="small"
                    dataSource={stream.events.slice(-200)}
                    renderItem={(e, idx) => (
                      <List.Item key={`evt-${idx}`}>
                        <Space>
                          <Tag>{String(e.stage ?? "info")}</Tag>
                          <Text>{String(e.message ?? "")}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                )}
              </Card>
              <Space>
                <Button
                  icon={<ThunderboltOutlined />}
                  type="primary"
                  onClick={() => router.push("/data/catalog")}
                >
                  Open Data Catalog
                </Button>
                <Button onClick={() => setStep(0)}>Start another</Button>
              </Space>
            </Space>
          ) : null}
        </div>
      </Card>

      <Card title="Tip" style={{ marginTop: 12 }}>
        <Paragraph>
          The pipeline groups files by stable filename family — e.g. CFPB&apos;s
          <Text code> 2022_public_lar_csv.zip / 2023_public_lar_csv.zip </Text>
          collapse into a single <Text code>lar</Text> table, FDA&apos;s
          <Text code> drug-event-NNNN-of-NNNN.json.zip </Text> series materializes as one
          <Text code> drug_event </Text> table, and so on. Set a row/file cap to keep
          multi-gigabyte ZIPs (USPTO patent filewrappers) bounded on the first ingest.
        </Paragraph>
      </Card>
    </PageContainer>
  );
}
