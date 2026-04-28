"use client";

import {
  CloudDownloadOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Drawer,
  Form,
  InputNumber,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";

const { Text, Paragraph } = Typography;

interface AlphaVantageFunction {
  id: string;
  label: string;
  category: string;
  function: string;
  domain: string;
  iceberg_table?: string | null;
  iceberg_identifier?: string | null;
  partition_spec?: Array<{ source_column: string; transform: string; name: string }>;
  lake_supported?: boolean;
}

interface FunctionsResponse {
  functions: AlphaVantageFunction[];
}

interface UniverseEntry {
  vt_symbol: string;
  ticker?: string;
  exchange?: string;
  asset_class?: string;
  name?: string;
}

interface UniverseResponse {
  items?: UniverseEntry[];
  total?: number;
  next_offset?: number | null;
  has_more?: boolean;
}

interface QueueResponse {
  task_id: string;
  stream_url: string;
}

const PAGE_SIZE = 250;

export function AlphaVantageBulkLoader() {
  const { message } = App.useApp();
  const [activeTab, setActiveTab] = useState<"all" | "filtered">("all");
  const [selectedEndpoints, setSelectedEndpoints] = useState<string[]>([
    "timeseries.daily_adjusted",
  ]);
  const [exchangeFilter, setExchangeFilter] = useState<string[]>([]);
  const [limit, setLimit] = useState<number | null>(50);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [universeOffset, setUniverseOffset] = useState(0);
  const [universeItems, setUniverseItems] = useState<UniverseEntry[]>([]);
  const [universeQuery, setUniverseQuery] = useState("");
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);

  const stream = useChatStream(taskId);

  const functions = useApiQuery<FunctionsResponse>({
    queryKey: ["alpha-vantage", "functions"],
    path: "/alpha-vantage/functions",
    staleTime: 5 * 60 * 1000,
  });

  const lakeFunctions = useMemo(
    () => (functions.data?.functions ?? []).filter((entry) => entry.lake_supported),
    [functions.data],
  );

  const universe = useApiQuery<UniverseResponse>({
    queryKey: ["data", "universe", "loader", universeQuery, universeOffset],
    path: "/data/universe",
    query: {
      limit: PAGE_SIZE,
      offset: universeOffset,
      query: universeQuery || undefined,
      source: "catalog",
    },
    enabled: activeTab === "filtered",
  });

  useEffect(() => {
    if (!universe.data?.items) return;
    setUniverseItems((previous) => {
      const merged = universeOffset === 0 ? universe.data?.items ?? [] : [...previous, ...(universe.data?.items ?? [])];
      const map = new Map<string, UniverseEntry>();
      for (const entry of merged) {
        if (entry.vt_symbol) map.set(entry.vt_symbol, entry);
      }
      return Array.from(map.values());
    });
  }, [universe.data, universeOffset]);

  useEffect(() => {
    setUniverseOffset(0);
    setUniverseItems([]);
  }, [universeQuery, activeTab]);

  const exchangeOptions = useMemo(() => {
    const set = new Set<string>();
    for (const entry of universeItems) {
      if (entry.exchange) set.add(entry.exchange);
    }
    return Array.from(set)
      .sort()
      .map((value) => ({ value, label: value }));
  }, [universeItems]);

  const totalSymbols = activeTab === "all" ? universe.data?.total ?? null : selectedSymbols.length;
  const rpm = 75;
  const expectedSeconds =
    totalSymbols && selectedEndpoints.length > 0
      ? Math.ceil((Number(totalSymbols) * selectedEndpoints.length * 60) / rpm)
      : null;

  async function queueAll() {
    if (selectedEndpoints.length === 0) {
      message.warning("Pick at least one endpoint");
      return;
    }
    try {
      const res = await apiFetch<QueueResponse>("/pipelines/alpha-vantage/endpoints", {
        method: "POST",
        body: JSON.stringify({
          endpoints: selectedEndpoints,
          symbols: "all_active",
          filters: exchangeFilter.length ? { exchange: exchangeFilter } : {},
          limit: limit ?? null,
          cache: true,
        }),
      });
      setTaskId(res.task_id);
      setDrawerOpen(true);
      message.success(`Bulk load queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function queueSelection() {
    if (selectedEndpoints.length === 0) {
      message.warning("Pick at least one endpoint");
      return;
    }
    if (selectedSymbols.length === 0) {
      message.warning("Pick at least one symbol");
      return;
    }
    try {
      const res = await apiFetch<QueueResponse>("/pipelines/alpha-vantage/endpoints", {
        method: "POST",
        body: JSON.stringify({
          endpoints: selectedEndpoints,
          symbols: selectedSymbols,
          cache: true,
        }),
      });
      setTaskId(res.task_id);
      setDrawerOpen(true);
      message.success(`Bulk load queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <Card
      size="small"
      title={
        <Space>
          <ThunderboltOutlined />
          <Text strong>AlphaVantage bulk loader</Text>
        </Space>
      }
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => functions.refetch()}>
          Refresh endpoints
        </Button>
      }
    >
      <Alert
        showIcon
        type="info"
        style={{ marginBottom: 12 }}
        message="Bulk loads write per-endpoint Iceberg tables under the aqp_alpha_vantage namespace, partitioned by symbol + month where applicable."
      />
      <Form layout="vertical">
        <Form.Item label="Endpoints">
          <Select
            mode="multiple"
            value={selectedEndpoints}
            onChange={setSelectedEndpoints}
            options={lakeFunctions.map((entry) => ({
              value: entry.id,
              label: `${entry.label} (${entry.iceberg_identifier ?? entry.function})`,
            }))}
            placeholder="Pick endpoints to materialize"
            showSearch
            filterOption={(input, option) =>
              String(option?.label ?? "").toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>
      </Form>

      <Tabs
        activeKey={activeTab}
        onChange={(value) => setActiveTab(value as "all" | "filtered")}
        items={[
          {
            key: "all",
            label: "Entire active universe",
            children: (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Form layout="inline">
                  <Form.Item label="Exchange filter">
                    <Select
                      mode="multiple"
                      style={{ minWidth: 240 }}
                      value={exchangeFilter}
                      onChange={setExchangeFilter}
                      options={[
                        { value: "NASDAQ", label: "NASDAQ" },
                        { value: "NYSE", label: "NYSE" },
                        { value: "ARCA", label: "ARCA" },
                        { value: "BATS", label: "BATS" },
                        ...exchangeOptions,
                      ]}
                      placeholder="(all exchanges)"
                    />
                  </Form.Item>
                  <Form.Item label="Cap (optional)">
                    <InputNumber min={1} value={limit ?? undefined} onChange={(v) => setLimit(v ? Number(v) : null)} />
                  </Form.Item>
                </Form>
                <Space>
                  <Statistic title="Endpoints" value={selectedEndpoints.length} />
                  <Statistic title="Symbols" value={limit ?? "all active"} />
                  <Statistic
                    title="Estimated runtime"
                    value={
                      expectedSeconds !== null
                        ? `${Math.ceil(expectedSeconds / 60)} min`
                        : "—"
                    }
                    suffix={
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        @ {rpm} rpm
                      </Text>
                    }
                  />
                </Space>
                <Button type="primary" icon={<CloudDownloadOutlined />} onClick={queueAll}>
                  Queue full load
                </Button>
              </Space>
            ),
          },
          {
            key: "filtered",
            label: "Filtered selection",
            children: (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Form layout="inline">
                  <Form.Item label="Search">
                    <Select
                      style={{ width: 240 }}
                      placeholder="Filter by ticker or vt_symbol"
                      showSearch
                      mode="tags"
                      value={universeQuery ? [universeQuery] : []}
                      onChange={(values) => setUniverseQuery(values[0] ?? "")}
                    />
                  </Form.Item>
                </Form>
                <Table
                  size="small"
                  rowSelection={{
                    type: "checkbox",
                    selectedRowKeys: selectedSymbols,
                    onChange: (keys) => setSelectedSymbols(keys.map((k) => String(k))),
                  }}
                  rowKey="vt_symbol"
                  dataSource={universeItems}
                  pagination={false}
                  columns={[
                    { title: "vt_symbol", dataIndex: "vt_symbol", key: "vt_symbol" },
                    { title: "Ticker", dataIndex: "ticker", key: "ticker" },
                    { title: "Exchange", dataIndex: "exchange", key: "exchange" },
                    { title: "Name", dataIndex: "name", key: "name" },
                  ]}
                  scroll={{ y: 320 }}
                />
                <Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {universeItems.length} of {universe.data?.total ?? "?"} loaded; {selectedSymbols.length} selected
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
                <Button type="primary" icon={<CloudDownloadOutlined />} onClick={queueSelection}>
                  Queue selection
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={taskId ? `Bulk load ${taskId}` : "Bulk load"}
        width={520}
      >
        {taskId ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Tag color={stream.status === "open" ? "blue" : stream.done ? "green" : "default"}>
              status: {stream.status} {stream.done ? "(done)" : ""}
            </Tag>
            <Paragraph copyable={{ text: taskId }}>Task: {taskId}</Paragraph>
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
              {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") || "—"}
            </pre>
            {stream.done ? (
              <Alert
                type="success"
                showIcon
                message="Bulk load complete"
                description={
                  <Space direction="vertical">
                    <Text>Open the data catalog to inspect new tables and refresh data links:</Text>
                    <Button type="link" href="/data/catalog">Open Data Catalog</Button>
                  </Space>
                }
              />
            ) : null}
          </Space>
        ) : (
          <Text type="secondary">Queue a load to start streaming progress.</Text>
        )}
      </Drawer>
    </Card>
  );
}
