"use client";

import {
  CloudDownloadOutlined,
  ExperimentOutlined,
  ExportOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Form,
  Input,
  List,
  Modal,
  Row,
  Select,
  Space,
  Steps,
  Tag,
  Typography,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useEffect, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";
import { useLiveStream } from "@/lib/ws/useLiveStream";

const { Text, Paragraph } = Typography;

interface CatalogRow {
  id: string;
  name: string;
  provider: string;
  domain: string;
  frequency?: string | null;
  latest_version?: number | null;
  latest_row_count?: number | null;
  updated_at: string;
}

interface IngestForm {
  symbols: string;
  range: [Dayjs, Dayjs];
  interval: string;
  source: string;
}

interface UniverseEntry {
  ticker?: string;
  vt_symbol?: string;
  name?: string;
  sector?: string;
}

interface UniverseResponse {
  items?: UniverseEntry[];
  source?: string;
}

interface SourceRow {
  name: string;
  display_name: string;
  enabled: boolean;
}

interface IndicatorEntry {
  id: string;
  name: string;
  group: string;
  description: string;
  params: { name: string; default: number | string | null }[];
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

interface StreamPreviewResponse {
  channel_id: string;
  ws_url: string;
}

interface PipelineExportResponse {
  feature_set_id?: string | null;
  feature_set_name: string;
  specs: string[];
  topic: string;
  persisted: boolean;
  error?: string | null;
}

const TRANSFORMATIONS: { value: string; label: string }[] = [
  { value: "Z:20", label: "Z-score (20)" },
  { value: "LogReturn:1", label: "Log return (1)" },
  { value: "ROC:12", label: "Rate of change (12)" },
  { value: "StdDev:20", label: "Std dev (20)" },
];

export function DataExplorer() {
  const { message } = App.useApp();
  const [form] = Form.useForm<IngestForm>();
  const [step, setStep] = useState(0);
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  const [symbols, setSymbols] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [selectedIndicators, setSelectedIndicators] = useState<string[]>([]);
  const [selectedFundamentals, setSelectedFundamentals] = useState<string[]>([]);
  const [transformations, setTransformations] = useState<string[]>([]);
  const [exportName, setExportName] = useState("data_browser_pipeline");
  const [exportOpen, setExportOpen] = useState(false);
  const [streamChannel, setStreamChannel] = useState<string | null>(null);

  const catalog = useApiQuery<CatalogRow[]>({
    queryKey: ["data", "catalog"],
    path: "/data/catalog",
    select: (raw) => (Array.isArray(raw) ? (raw as CatalogRow[]) : []),
  });

  const universe = useApiQuery<UniverseResponse>({
    queryKey: ["data", "universe", "explorer"],
    path: "/data/universe",
    query: { limit: 500 },
    staleTime: 60_000,
  });

  const sourcesQuery = useApiQuery<SourceRow[]>({
    queryKey: ["sources", "list-all"],
    path: "/sources/",
    select: (raw) => (Array.isArray(raw) ? (raw as SourceRow[]) : []),
  });

  const indicatorCatalog = useApiQuery<CatalogResponse>({
    queryKey: ["indicator-catalog"],
    path: "/data/indicators/catalog",
    staleTime: 5 * 60 * 1000,
  });

  const featureCandidates = useApiQuery<FeatureCandidatesResponse>({
    queryKey: ["feature-catalog", "candidates", "all"],
    path: "/feature-catalog/candidates",
    query: { limit: 500 },
    staleTime: 5 * 60 * 1000,
  });

  const liveStream = useLiveStream({ channelId: streamChannel, bufferSize: 200 });

  const universeOptions = useMemo(() => {
    return (universe.data?.items ?? []).map((it) => {
      const vt = it.vt_symbol ?? `${it.ticker ?? ""}.NASDAQ`;
      return { value: vt, label: vt };
    });
  }, [universe.data]);

  const sourceOptions = useMemo(() => {
    return (sourcesQuery.data ?? []).map((s) => ({
      value: s.name,
      label: s.display_name,
      disabled: !s.enabled,
    }));
  }, [sourcesQuery.data]);

  const indicatorOptions = useMemo(() => {
    const all = (indicatorCatalog.data?.groups ?? []).flatMap((g) => g.indicators);
    return all.map((ind) => {
      const period = ind.params.find((p) => p.name === "timeperiod")?.default;
      const spec = period ? `${ind.name}:${period}` : ind.name;
      return { value: spec, label: `${ind.name} — ${ind.group}` };
    });
  }, [indicatorCatalog.data]);

  const fundamentalOptions = useMemo(() => {
    return (featureCandidates.data?.candidates ?? []).map((c) => ({
      value: `${c.source}.${c.domain}.${c.field}`,
      label: `${c.field} (${c.source}.${c.domain})`,
    }));
  }, [featureCandidates.data]);

  useEffect(() => {
    return () => {
      // cleanup any open stream
      if (streamChannel) {
        apiFetch(`/live/subscribe/${streamChannel}`, { method: "DELETE" }).catch(() => {
          /* noop */
        });
      }
    };
  }, [streamChannel]);

  async function submit() {
    const values = await form.validateFields();
    const payload = {
      symbols: values.symbols
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean),
      start: values.range[0].format("YYYY-MM-DD"),
      end: values.range[1].format("YYYY-MM-DD"),
      interval: values.interval,
      source: values.source,
    };
    if (payload.symbols.length === 0) {
      message.warning("Add at least one symbol");
      return;
    }
    try {
      const res = await apiFetch<{ task_id: string }>("/data/ingest", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setTaskId(res.task_id);
      setStep(2);
      message.success(`Ingest queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function startStreamPreview() {
    if (symbols.length === 0) {
      message.warning("Pick at least one security");
      return;
    }
    try {
      const res = await apiFetch<StreamPreviewResponse>("/data/preview/stream", {
        method: "POST",
        body: JSON.stringify({
          venue: "simulated",
          symbols,
          indicators: selectedIndicators,
          transformations,
          poll_cadence_seconds: 5,
        }),
      });
      setStreamChannel(res.channel_id);
      message.success(`Preview channel ${res.channel_id} opened`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function stopStreamPreview() {
    if (!streamChannel) return;
    try {
      await apiFetch(`/live/subscribe/${streamChannel}`, { method: "DELETE" });
      message.success("Stream closed");
    } catch (err) {
      message.error((err as Error).message);
    }
    setStreamChannel(null);
  }

  async function exportPipeline() {
    try {
      const res = await apiFetch<PipelineExportResponse>("/pipelines/from-browser", {
        method: "POST",
        body: JSON.stringify({
          name: exportName,
          symbols,
          sources,
          indicators: selectedIndicators,
          fundamentals: selectedFundamentals,
          transformations,
        }),
      });
      if (res.persisted) {
        message.success(`Pipeline saved (id ${res.feature_set_id})`);
      } else {
        message.warning(`Pipeline compiled but not persisted: ${res.error ?? "unknown"}`);
      }
      setExportOpen(false);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Data Explorer"
      subtitle="Compose a securities + sources + indicators + transformations pipeline."
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => catalog.refetch()}>
            Refresh
          </Button>
        </Space>
      }
    >
      <Card
        title="Pipeline composer"
        size="small"
        style={{ marginBottom: 16 }}
        extra={
          <Space>
            <Button
              icon={<PlayCircleOutlined />}
              onClick={streamChannel ? stopStreamPreview : startStreamPreview}
              type={streamChannel ? "default" : "primary"}
            >
              {streamChannel ? "Stop preview" : "Stream preview"}
            </Button>
            <Button icon={<ExportOutlined />} onClick={() => setExportOpen(true)}>
              Export to pipeline
            </Button>
          </Space>
        }
      >
        <Row gutter={12}>
          <Col xs={24} md={12} lg={8}>
            <div style={{ marginBottom: 4 }}>
              <Text strong>Securities</Text>
            </div>
            <Select
              mode="multiple"
              placeholder="Pick symbols from the universe"
              value={symbols}
              onChange={setSymbols}
              options={universeOptions}
              style={{ width: "100%" }}
              maxTagCount={4}
              showSearch
              filterOption={(input, option) =>
                String(option?.label ?? "")
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
            <Text type="secondary" style={{ fontSize: 11 }}>
              {(universe.data?.items ?? []).length} symbols indexed (source:{" "}
              {universe.data?.source ?? "—"})
            </Text>
          </Col>
          <Col xs={24} md={12} lg={8}>
            <div style={{ marginBottom: 4 }}>
              <Text strong>Sources</Text>
            </div>
            <Select
              mode="multiple"
              placeholder="Pick data sources"
              value={sources}
              onChange={setSources}
              options={sourceOptions}
              style={{ width: "100%" }}
              maxTagCount={4}
            />
          </Col>
          <Col xs={24} md={12} lg={8}>
            <div style={{ marginBottom: 4 }}>
              <Text strong>Indicators</Text>{" "}
              <Tag icon={<ExperimentOutlined />} color="purple">
                TA-Lib
              </Tag>
            </div>
            <Select
              mode="multiple"
              placeholder="Pick indicators"
              value={selectedIndicators}
              onChange={setSelectedIndicators}
              options={indicatorOptions}
              style={{ width: "100%" }}
              maxTagCount={4}
              showSearch
              filterOption={(input, option) =>
                String(option?.label ?? "")
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
          </Col>
          <Col xs={24} md={12} lg={8} style={{ marginTop: 12 }}>
            <div style={{ marginBottom: 4 }}>
              <Text strong>Fundamentals</Text>
            </div>
            <Select
              mode="multiple"
              placeholder="Pick feed fields"
              value={selectedFundamentals}
              onChange={setSelectedFundamentals}
              options={fundamentalOptions}
              style={{ width: "100%" }}
              maxTagCount={4}
              showSearch
              filterOption={(input, option) =>
                String(option?.label ?? "")
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
          </Col>
          <Col xs={24} md={12} lg={8} style={{ marginTop: 12 }}>
            <div style={{ marginBottom: 4 }}>
              <Text strong>Transformations</Text>
            </div>
            <Select
              mode="multiple"
              placeholder="Apply transformations"
              value={transformations}
              onChange={setTransformations}
              options={TRANSFORMATIONS}
              style={{ width: "100%" }}
            />
          </Col>
        </Row>
        {streamChannel ? (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 12 }}
            message={`Streaming on channel ${streamChannel} (${liveStream.status})`}
            description={
              liveStream.buffer.length > 0
                ? `Latest: ${liveStream.buffer.length} events buffered`
                : "Waiting for first event…"
            }
          />
        ) : null}
      </Card>
      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="Ingest wizard" size="small">
            <Steps
              current={step}
              size="small"
              items={[
                { title: "Universe" },
                { title: "Range" },
                { title: "Stream" },
              ]}
              style={{ marginBottom: 16 }}
            />
            <Form<IngestForm>
              form={form}
              layout="vertical"
              initialValues={{
                symbols: "SPY, AAPL, MSFT",
                interval: "1d",
                source: "yahoo",
                range: [dayjs().subtract(2, "year"), dayjs()],
              }}
              onValuesChange={() => setStep((s) => Math.max(s, 1))}
            >
              <Form.Item
                label="Symbols"
                name="symbols"
                rules={[{ required: true, message: "Required" }]}
              >
                <Input.TextArea autoSize placeholder="SPY, AAPL, MSFT" />
              </Form.Item>
              <Form.Item
                label="Range"
                name="range"
                rules={[{ required: true, message: "Required" }]}
              >
                <DatePicker.RangePicker style={{ width: "100%" }} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item label="Interval" name="interval">
                    <Select
                      options={[
                        { value: "1d", label: "Daily" },
                        { value: "1h", label: "Hourly" },
                        { value: "5m", label: "5-minute" },
                        { value: "1m", label: "1-minute" },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Source" name="source">
                    <Select
                      options={[
                        { value: "yahoo", label: "yfinance" },
                        { value: "alpaca", label: "Alpaca" },
                        { value: "ibkr", label: "IBKR" },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" icon={<CloudDownloadOutlined />} onClick={submit}>
                Queue ingest
              </Button>
            </Form>
          </Card>
          {taskId ? (
            <Card title="Stream" size="small" style={{ marginTop: 16 }}>
              <Paragraph copyable={{ text: taskId }}>Task: {taskId}</Paragraph>
              <Text type="secondary">Status: {stream.status}</Text>
              <pre
                style={{
                  marginTop: 8,
                  fontSize: 11,
                  maxHeight: 220,
                  overflow: "auto",
                  background: "var(--ant-color-bg-elevated)",
                  padding: 8,
                  borderRadius: 6,
                }}
              >
                {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") || "—"}
              </pre>
            </Card>
          ) : null}
          {streamChannel ? (
            <Card title="Live preview" size="small" style={{ marginTop: 16 }}>
              <List
                size="small"
                dataSource={liveStream.buffer.slice(-10).reverse()}
                locale={{ emptyText: "Waiting…" }}
                renderItem={(ev) => (
                  <List.Item style={{ padding: "4px 0" }}>
                    <Space size={6}>
                      <Tag color="purple">{ev.kind}</Tag>
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
            </Card>
          ) : null}
        </Col>
        <Col xs={24} lg={14}>
          <Card title="Catalog" size="small">
            {(catalog.data ?? []).length === 0 ? (
              <Text type="secondary">No datasets indexed yet.</Text>
            ) : (
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                {(catalog.data ?? []).slice(0, 12).map((row) => (
                  <Descriptions
                    key={row.id}
                    size="small"
                    bordered
                    column={4}
                    items={[
                      {
                        key: "name",
                        label: "Name",
                        children: (
                          <Space>
                            <Text strong>{row.name}</Text>
                            <Tag>{row.provider}</Tag>
                            <Tag color="blue">{row.domain}</Tag>
                          </Space>
                        ),
                        span: 4,
                      },
                      { key: "v", label: "Latest", children: `v${row.latest_version ?? "?"}` },
                      { key: "rows", label: "Rows", children: row.latest_row_count ?? "—" },
                      { key: "freq", label: "Frequency", children: row.frequency ?? "—" },
                      { key: "ts", label: "Updated", children: row.updated_at },
                    ]}
                  />
                ))}
              </Space>
            )}
          </Card>
        </Col>
      </Row>
      <Modal
        open={exportOpen}
        title="Export pipeline to feature set"
        okText="Export"
        onOk={exportPipeline}
        onCancel={() => setExportOpen(false)}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Text type="secondary">
            Compiles the current selection into a named feature set (and emits to a Kafka topic).
          </Text>
          <Input
            value={exportName}
            onChange={(e) => setExportName(e.target.value)}
            placeholder="feature_set_name"
          />
          <Descriptions column={1} size="small" items={[
            { key: "sym", label: "Securities", children: symbols.join(", ") || "—" },
            { key: "src", label: "Sources", children: sources.join(", ") || "—" },
            { key: "ind", label: "Indicators", children: selectedIndicators.join(", ") || "—" },
            { key: "fnd", label: "Fundamentals", children: selectedFundamentals.join(", ") || "—" },
            { key: "tx", label: "Transforms", children: transformations.join(", ") || "—" },
          ]} />
        </Space>
      </Modal>
    </PageContainer>
  );
}
