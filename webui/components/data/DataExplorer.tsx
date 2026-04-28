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
  InputNumber,
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
  avFunction: string;
  outputsize: string;
  month?: string;
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
  count?: number;
  total?: number;
  next_offset?: number | null;
  has_more?: boolean;
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
  const [universeSource, setUniverseSource] = useState("managed_snapshot");
  const [universeState, setUniverseState] = useState("active");
  const [includeOtc, setIncludeOtc] = useState(false);
  const [universeSearch, setUniverseSearch] = useState("");
  const [universeOffset, setUniverseOffset] = useState(0);
  const [universePageSize, setUniversePageSize] = useState(1000);
  const [universeItems, setUniverseItems] = useState<UniverseEntry[]>([]);

  const catalog = useApiQuery<CatalogRow[]>({
    queryKey: ["data", "catalog"],
    path: "/data/catalog",
    select: (raw) => (Array.isArray(raw) ? (raw as CatalogRow[]) : []),
  });

  const universe = useApiQuery<UniverseResponse>({
    queryKey: [
      "data",
      "universe",
      "explorer",
      universeSource,
      universeState,
      includeOtc,
      universeSearch,
      universeOffset,
      universePageSize,
    ],
    path: "/data/universe",
    query: {
      limit: universePageSize,
      offset: universeOffset,
      query: universeSearch || undefined,
      source: universeSource,
      state: universeState,
      include_otc: includeOtc,
    },
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

  useEffect(() => {
    const items = universe.data?.items ?? [];
    setUniverseItems((previous) => {
      const merged = universeOffset === 0 ? items : [...previous, ...items];
      const bySymbol = new Map<string, UniverseEntry>();
      for (const item of merged) {
        const key = item.vt_symbol ?? item.ticker;
        if (key) bySymbol.set(key, item);
      }
      return Array.from(bySymbol.values());
    });
  }, [universe.data, universeOffset]);

  useEffect(() => {
    setUniverseOffset(0);
    setUniverseItems([]);
  }, [universeSource, universeState, includeOtc, universeSearch, universePageSize]);

  const universeOptions = useMemo(() => {
    return universeItems.map((it) => {
      const vt = it.vt_symbol ?? `${it.ticker ?? ""}.NASDAQ`;
      return { value: vt, label: it.name ? `${vt} — ${it.name}` : vt };
    });
  }, [universeItems]);

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
      const endpoint = values.source === "alpha_vantage" ? "/pipelines/alpha-vantage/history" : "/data/ingest";
      const resolvedAvFunction =
        values.avFunction || (payload.interval === "1d" ? "daily_adjusted" : "intraday");
      const mappedAvInterval = toAlphaVantageInterval(payload.interval);
      const body = values.source === "alpha_vantage"
        ? {
            symbols: payload.symbols,
            start: payload.start,
            end: payload.end,
            function: resolvedAvFunction,
            interval:
              mappedAvInterval ?? (resolvedAvFunction === "intraday" ? "5min" : undefined),
            outputsize: values.outputsize || "full",
            month: values.month || undefined,
            cache: true,
          }
        : payload;
      const res = await apiFetch<{ task_id: string }>(endpoint, {
        method: "POST",
        body: JSON.stringify(body),
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

  async function syncUniverse() {
    try {
      const res = await apiFetch<{ task_id: string }>("/data/universe/sync", {
        method: "POST",
        body: JSON.stringify({
          state: universeState,
          limit: null,
          include_otc: includeOtc,
          query: universeSearch || null,
        }),
      });
      setTaskId(res.task_id);
      message.success(`Universe sync queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  function useSelectedUniverseSymbols() {
    if (symbols.length === 0) {
      message.warning("Pick at least one security first");
      return;
    }
    form.setFieldValue("symbols", symbols.join(", "));
    message.success(`Copied ${symbols.length} selected securities into the ingest form`);
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
            <Space wrap style={{ marginBottom: 8 }}>
              <Select
                size="small"
                value={universeSource}
                onChange={setUniverseSource}
                style={{ width: 180 }}
                options={[
                  { value: "managed_snapshot", label: "Managed snapshot" },
                  { value: "alpha_vantage", label: "AlphaVantage live" },
                  { value: "catalog", label: "Data catalog" },
                  { value: "config", label: "Config fallback" },
                ]}
              />
              <Select
                size="small"
                value={universeState}
                onChange={setUniverseState}
                style={{ width: 110 }}
                options={[
                  { value: "active", label: "Active" },
                  { value: "delisted", label: "Delisted" },
                ]}
              />
              <Select
                size="small"
                value={includeOtc ? "yes" : "no"}
                onChange={(value) => setIncludeOtc(value === "yes")}
                style={{ width: 110 }}
                options={[
                  { value: "no", label: "No OTC" },
                  { value: "yes", label: "Include OTC" },
                ]}
              />
              <Button size="small" onClick={syncUniverse}>
                Sync AV
              </Button>
            </Space>
            <Select
              mode="multiple"
              placeholder="Search and pick symbols from the universe"
              value={symbols}
              onChange={setSymbols}
              onSearch={setUniverseSearch}
              options={universeOptions}
              style={{ width: "100%" }}
              maxTagCount={4}
              showSearch
              filterOption={false}
            />
            <Space wrap style={{ marginTop: 6 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {universeItems.length} loaded of {universe.data?.total ?? "?"} symbols (source:{" "}
                {universe.data?.source ?? "—"})
              </Text>
              {universe.data?.has_more ? (
                <Button
                  size="small"
                  onClick={() => setUniverseOffset(universe.data?.next_offset ?? universeItems.length)}
                  loading={universe.isFetching}
                >
                  Load more
                </Button>
              ) : null}
            </Space>
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
                avFunction: "daily_adjusted",
                outputsize: "full",
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
              <Button size="small" onClick={useSelectedUniverseSymbols} style={{ marginBottom: 12 }}>
                Use selected universe symbols
              </Button>
              <Form.Item
                label="History range"
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
                        { value: "30m", label: "30-minute" },
                        { value: "15m", label: "15-minute" },
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
                        { value: "alpha_vantage", label: "AlphaVantage → Iceberg" },
                        { value: "alpaca", label: "Alpaca" },
                        { value: "ibkr", label: "IBKR" },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item label="AlphaVantage function" name="avFunction">
                    <Select
                      options={[
                        { value: "daily_adjusted", label: "Daily adjusted" },
                        { value: "daily", label: "Daily raw" },
                        { value: "intraday", label: "Intraday" },
                        { value: "weekly_adjusted", label: "Weekly adjusted" },
                        { value: "monthly_adjusted", label: "Monthly adjusted" },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="Output size" name="outputsize">
                    <Select
                      options={[
                        { value: "compact", label: "Compact" },
                        { value: "full", label: "Full" },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="Page size">
                    <InputNumber
                      min={100}
                      max={5000}
                      step={100}
                      value={universePageSize}
                      onChange={(value) => setUniversePageSize(Number(value ?? 1000))}
                      style={{ width: "100%" }}
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

function toAlphaVantageInterval(interval: string): string | null {
  const mapping: Record<string, string> = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "60min",
  };
  return mapping[interval] ?? null;
}
