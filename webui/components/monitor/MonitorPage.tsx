"use client";

import { ExportOutlined, LineChartOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  List,
  Row,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import { apiFetch } from "@/lib/api/client";
import { useLiveStream } from "@/lib/ws/useLiveStream";

const { Text } = Typography;
const DASH_URL = process.env.NEXT_PUBLIC_DASH_URL ?? "http://localhost:8000/dash/";

interface HealthResponse {
  status: string;
  ollama: boolean;
  redis: boolean;
  postgres: boolean;
  chromadb: boolean;
  vllm: boolean;
}

interface UniverseEntry {
  ticker?: string;
  vt_symbol?: string;
  name?: string;
  sector?: string;
  exchange?: string;
}

interface UniverseResponse {
  items?: UniverseEntry[];
  source?: string;
}

interface AgentDecision {
  id: string;
  vt_symbol: string;
  ts: string;
  action: string;
  size_pct: number;
  confidence: number;
  rating?: string;
  rationale?: string;
  provider?: string;
}

interface OrderRow {
  id?: string;
  vt_symbol?: string;
  side?: string;
  qty?: number;
  status?: string;
  created_at?: string;
}

interface FillRow {
  id?: string;
  vt_symbol?: string;
  side?: string;
  qty?: number;
  price?: number;
  ts?: string;
  filled_at?: string;
}

interface PositionRow {
  vt_symbol?: string;
  qty?: number;
  avg_price?: number;
  market_value?: number;
  unrealized_pnl?: number;
}

interface SubscribeResponse {
  channel_id: string;
  ws_url: string;
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <Tag color={ok ? "green" : "red"} style={{ marginRight: 4 }}>
      {label}: {ok ? "ok" : "down"}
    </Tag>
  );
}

export function MonitorPage() {
  return (
    <Suspense fallback={null}>
      <MonitorPageInner />
    </Suspense>
  );
}

function MonitorPageInner() {
  const params = useSearchParams();
  const legacy = params?.get("legacy") === "1";
  const [channelId, setChannelId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);

  const health = useApiQuery<HealthResponse>({
    queryKey: ["health"],
    path: "/health",
    refetchInterval: 15_000,
  });

  const universe = useApiQuery<UniverseResponse>({
    queryKey: ["data", "universe", "monitor"],
    path: "/data/universe",
    query: { limit: 500 },
    staleTime: 60_000,
  });

  const decisions = useApiQuery<AgentDecision[]>({
    queryKey: ["agentic", "decisions", "recent"],
    path: "/agentic/decisions",
    query: { limit: 100 },
    refetchInterval: 5000,
  });

  const orders = useApiQuery<{ items?: OrderRow[] } | OrderRow[]>({
    queryKey: ["portfolio", "orders"],
    path: "/portfolio/orders",
    query: { limit: 50 },
    refetchInterval: 5000,
  });

  const fills = useApiQuery<{ items?: FillRow[] } | FillRow[]>({
    queryKey: ["portfolio", "fills"],
    path: "/portfolio/fills",
    query: { limit: 50 },
    refetchInterval: 5000,
  });

  const positions = useApiQuery<{ items?: PositionRow[] } | PositionRow[]>({
    queryKey: ["portfolio", "positions"],
    path: "/portfolio/positions",
    refetchInterval: 5000,
  });

  const stream = useLiveStream({ channelId: streaming ? channelId : null, bufferSize: 256 });

  function asArray<T>(res: { items?: T[] } | T[] | undefined): T[] {
    if (!res) return [];
    if (Array.isArray(res)) return res;
    return res.items ?? [];
  }

  const orderRows = asArray<OrderRow>(orders.data);
  const fillRows = asArray<FillRow>(fills.data);
  const positionRows = asArray<PositionRow>(positions.data);

  async function startStream() {
    try {
      const symbols = (universe.data?.items ?? [])
        .slice(0, 6)
        .map((it) => it.vt_symbol ?? it.ticker)
        .filter((s): s is string => Boolean(s));
      if (symbols.length === 0) return;
      const resp = await apiFetch<SubscribeResponse>("/live/subscribe", {
        method: "POST",
        body: JSON.stringify({ venue: "simulated", symbols, poll_cadence_seconds: 5 }),
      });
      setChannelId(resp.channel_id);
      setStreaming(true);
    } catch {
      setStreaming(false);
    }
  }

  async function stopStream() {
    if (channelId) {
      try {
        await apiFetch(`/live/subscribe/${channelId}`, { method: "DELETE" });
      } catch {
        /* ignore */
      }
    }
    setStreaming(false);
    setChannelId(null);
  }

  const sectorBreakdown = useMemo(() => {
    const items = universe.data?.items ?? [];
    const counts: Record<string, number> = {};
    for (const it of items) {
      const sector = it.sector ?? "—";
      counts[sector] = (counts[sector] ?? 0) + 1;
    }
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 12)
      .map(([sector, count]) => ({ sector, count }));
  }, [universe.data]);

  const totalEquity = positionRows.reduce(
    (acc, p) => acc + (Number(p.market_value) || 0),
    0,
  );
  const totalUpnl = positionRows.reduce(
    (acc, p) => acc + (Number(p.unrealized_pnl) || 0),
    0,
  );

  if (legacy) {
    return (
      <PageContainer
        title="Strategy Monitor (legacy)"
        subtitle="Embedded Dash dashboard — kept available via ?legacy=1."
        extra={
          <Button icon={<ExportOutlined />} href={DASH_URL} target="_blank" rel="noreferrer">
            Open in new tab
          </Button>
        }
      >
        <Card styles={{ body: { padding: 0 } }}>
          <iframe
            src={DASH_URL}
            title="Strategy Monitor"
            style={{
              width: "100%",
              height: "calc(100vh - 220px)",
              border: 0,
              borderRadius: 6,
              background: "#fff",
            }}
          />
        </Card>
      </PageContainer>
    );
  }

  return (
    <PageContainer
      title="Live Monitor"
      subtitle="Decisions, signals, positions, and universe status in one view."
      extra={
        <Space>
          <Switch
            checked={streaming}
            checkedChildren="streaming"
            unCheckedChildren="stream off"
            onChange={(v) => (v ? startStream() : stopStream())}
          />
          <Button icon={<ReloadOutlined />} onClick={() => decisions.refetch()}>
            Refresh
          </Button>
          <Button href="?legacy=1">Legacy Dash</Button>
        </Space>
      }
    >
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <StatusPill ok={Boolean(health.data?.redis)} label="redis" />
          <StatusPill ok={Boolean(health.data?.postgres)} label="postgres" />
          <StatusPill ok={Boolean(health.data?.chromadb)} label="chroma" />
          <StatusPill ok={Boolean(health.data?.ollama)} label="ollama" />
          <StatusPill ok={Boolean(health.data?.vllm)} label="vllm" />
          <Tag color="blue">stream: {stream.status}</Tag>
          {stream.error ? <Tag color="red">{stream.error}</Tag> : null}
        </Space>
      </Card>
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="Portfolio" size="small">
            <Statistic
              title="Total market value"
              value={totalEquity}
              precision={2}
              prefix="$"
            />
            <Statistic
              title="Unrealized P/L"
              value={totalUpnl}
              precision={2}
              prefix="$"
              valueStyle={{ color: totalUpnl >= 0 ? "#10b981" : "#ef4444" }}
            />
            <Descriptions column={1} size="small" style={{ marginTop: 12 }}>
              <Descriptions.Item label="Positions">{positionRows.length}</Descriptions.Item>
              <Descriptions.Item label="Pending orders">{orderRows.length}</Descriptions.Item>
              <Descriptions.Item label="Recent fills">{fillRows.length}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Stock universe" size="small">
            <Statistic
              title="Tickers"
              value={(universe.data?.items ?? []).length}
              prefix={<LineChartOutlined />}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              source: {universe.data?.source ?? "—"}
            </Text>
            <div style={{ marginTop: 10 }}>
              {sectorBreakdown.map((row) => (
                <Tag key={row.sector} style={{ marginBottom: 4 }}>
                  {row.sector}: {row.count}
                </Tag>
              ))}
              {sectorBreakdown.length === 0 ? <Text type="secondary">—</Text> : null}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Live signals" size="small">
            {streaming ? (
              <List
                size="small"
                dataSource={stream.buffer.slice(-10).reverse()}
                locale={{ emptyText: "Waiting for signals…" }}
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
                      {"direction" in ev ? <Tag>{ev.direction}</Tag> : null}
                      {"close" in ev ? (
                        <Text style={{ fontSize: 12 }}>{ev.close.toFixed(2)}</Text>
                      ) : null}
                    </Space>
                  </List.Item>
                )}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="Toggle streaming to subscribe to live bars/quotes/signals."
              />
            )}
          </Card>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title={<Space>Buy/Sell decisions <Badge count={decisions.data?.length ?? 0} /></Space>} size="small">
            {decisions.error ? <Alert type="error" message={decisions.error.message} /> : null}
            <Table
              size="small"
              rowKey={(r) => r.id ?? `${r.vt_symbol}-${r.ts}`}
              dataSource={(decisions.data ?? []).slice(0, 50)}
              pagination={{ pageSize: 10 }}
              columns={[
                { title: "ts", dataIndex: "ts", width: 160 },
                { title: "symbol", dataIndex: "vt_symbol", width: 120 },
                {
                  title: "action",
                  dataIndex: "action",
                  width: 80,
                  render: (a: string) => (
                    <Tag color={a === "BUY" ? "green" : a === "SELL" ? "red" : "default"}>{a}</Tag>
                  ),
                },
                {
                  title: "size",
                  dataIndex: "size_pct",
                  width: 90,
                  render: (v: number) => (v != null ? `${(v * 100).toFixed(1)}%` : "—"),
                },
                { title: "rationale", dataIndex: "rationale", ellipsis: true },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={<Space>Recent orders <Badge count={orderRows.length} /></Space>} size="small">
            <Table
              size="small"
              rowKey={(r) => r.id ?? `${r.vt_symbol}-${r.created_at}`}
              dataSource={orderRows.slice(0, 50)}
              pagination={{ pageSize: 10 }}
              columns={[
                { title: "created", dataIndex: "created_at", width: 170 },
                { title: "symbol", dataIndex: "vt_symbol", width: 120 },
                { title: "side", dataIndex: "side", width: 80 },
                { title: "qty", dataIndex: "qty", width: 80 },
                { title: "status", dataIndex: "status", width: 100 },
              ]}
            />
          </Card>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title={<Space>Positions <Badge count={positionRows.length} /></Space>} size="small">
            <Table
              size="small"
              rowKey={(r) => r.vt_symbol ?? "—"}
              dataSource={positionRows}
              pagination={false}
              columns={[
                { title: "symbol", dataIndex: "vt_symbol", width: 120 },
                { title: "qty", dataIndex: "qty", width: 80 },
                {
                  title: "avg",
                  dataIndex: "avg_price",
                  width: 90,
                  render: (v: number) => (v != null ? Number(v).toFixed(2) : "—"),
                },
                {
                  title: "MV",
                  dataIndex: "market_value",
                  width: 110,
                  render: (v: number) => (v != null ? `$${Number(v).toFixed(2)}` : "—"),
                },
                {
                  title: "uPnL",
                  dataIndex: "unrealized_pnl",
                  width: 110,
                  render: (v: number) =>
                    v != null ? (
                      <Text style={{ color: v >= 0 ? "#10b981" : "#ef4444" }}>${Number(v).toFixed(2)}</Text>
                    ) : (
                      "—"
                    ),
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={<Space>Recent fills <Badge count={fillRows.length} /></Space>} size="small">
            <Table
              size="small"
              rowKey={(r) => r.id ?? `${r.vt_symbol}-${r.ts ?? r.filled_at ?? Math.random()}`}
              dataSource={fillRows.slice(0, 50)}
              pagination={{ pageSize: 10 }}
              columns={[
                { title: "ts", dataIndex: "filled_at", width: 170 },
                { title: "symbol", dataIndex: "vt_symbol", width: 120 },
                {
                  title: "side",
                  dataIndex: "side",
                  width: 80,
                  render: (s: string) => (
                    <Tag color={s === "BUY" ? "green" : s === "SELL" ? "red" : undefined}>{s}</Tag>
                  ),
                },
                { title: "qty", dataIndex: "qty", width: 80 },
                {
                  title: "price",
                  dataIndex: "price",
                  width: 90,
                  render: (v: number) => (v != null ? Number(v).toFixed(2) : "—"),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
