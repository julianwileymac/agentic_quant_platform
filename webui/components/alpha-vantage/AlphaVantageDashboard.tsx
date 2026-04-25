"use client";

import {
  BarChartOutlined,
  DollarOutlined,
  FundOutlined,
  GlobalOutlined,
  LineChartOutlined,
  RiseOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Alert, Card, Col, Row, Space, Statistic, Table, Tag, Typography } from "antd";
import Link from "next/link";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface HealthPayload {
  enabled: boolean;
  credentials_loaded: boolean;
  rpm_limit: number;
  daily_limit: number;
  cache_backend: string;
  message?: string | null;
}

interface UsagePayload {
  rpm_limit: number;
  daily_limit: number;
  requests_this_minute: number;
  requests_today: number;
  tokens_available: number;
}

interface TopMoversPayload {
  top_gainers?: Array<Record<string, unknown>>;
  top_losers?: Array<Record<string, unknown>>;
}

const tiles = [
  { href: "/alpha-vantage/timeseries", label: "Time Series", icon: <LineChartOutlined />, desc: "Intraday, daily, weekly, monthly OHLCV" },
  { href: "/alpha-vantage/fundamentals", label: "Fundamentals", icon: <FundOutlined />, desc: "Overview, statements, earnings, corporate actions" },
  { href: "/alpha-vantage/technicals", label: "Technicals", icon: <BarChartOutlined />, desc: "SMA, EMA, MACD, RSI and 50+ indicators" },
  { href: "/alpha-vantage/intelligence", label: "Intelligence", icon: <RiseOutlined />, desc: "News sentiment, movers, insider activity" },
  { href: "/alpha-vantage/forex", label: "Forex", icon: <GlobalOutlined />, desc: "FX rates and historical currency series" },
  { href: "/alpha-vantage/crypto", label: "Crypto", icon: <DollarOutlined />, desc: "Crypto rates and digital currency bars" },
  { href: "/alpha-vantage/options", label: "Options", icon: <RiseOutlined />, desc: "Realtime and historical option chains" },
  { href: "/alpha-vantage/commodities", label: "Commodities", icon: <BarChartOutlined />, desc: "Energy, metals, agriculture, global index" },
  { href: "/alpha-vantage/economics", label: "Economics", icon: <FundOutlined />, desc: "GDP, CPI, treasury yields, federal funds" },
  { href: "/alpha-vantage/indices", label: "Indices", icon: <LineChartOutlined />, desc: "Index series and catalog endpoints" },
  { href: "/alpha-vantage/admin", label: "Admin", icon: <SettingOutlined />, desc: "Bulk-load jobs and provider controls" },
];

export function AlphaVantageDashboard() {
  const health = useApiQuery<HealthPayload>({
    queryKey: ["alpha-vantage", "health"],
    path: "/alpha-vantage/health",
    refetchInterval: 60_000,
  });
  const usage = useApiQuery<UsagePayload>({
    queryKey: ["alpha-vantage", "usage"],
    path: "/alpha-vantage/usage",
    enabled: Boolean(health.data?.enabled && health.data?.credentials_loaded),
    refetchInterval: 30_000,
  });
  const movers = useApiQuery<TopMoversPayload>({
    queryKey: ["alpha-vantage", "top-movers"],
    path: "/alpha-vantage/intelligence/top-movers",
    enabled: Boolean(health.data?.enabled && health.data?.credentials_loaded),
    refetchInterval: 60_000,
  });

  return (
    <PageContainer
      title="Alpha Vantage"
      subtitle="Primary market-data provider for quotes, fundamentals, news, options, FX, crypto, commodities, economics, and technical indicators."
    >
      {health.data && !health.data.credentials_loaded ? (
        <Alert
          type="warning"
          showIcon
          message="Alpha Vantage credentials are not configured"
          description="Set AQP_ALPHA_VANTAGE_API_KEY or AQP_ALPHA_VANTAGE_API_KEY_FILE to enable live provider calls."
          style={{ marginBottom: 16 }}
        />
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="Provider"
              value={health.data?.enabled ? "Enabled" : "Disabled"}
              suffix={<Tag color={health.data?.credentials_loaded ? "green" : "orange"}>{health.data?.credentials_loaded ? "key loaded" : "no key"}</Tag>}
            />
            <Text type="secondary">Cache: {health.data?.cache_backend ?? "n/a"}</Text>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="Requests this minute" value={usage.data?.requests_this_minute ?? 0} suffix={`/ ${usage.data?.rpm_limit ?? health.data?.rpm_limit ?? 0}`} />
            <Text type="secondary">Tokens: {usage.data?.tokens_available ?? "n/a"}</Text>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="Requests today" value={usage.data?.requests_today ?? 0} suffix={usage.data?.daily_limit ? `/ ${usage.data.daily_limit}` : ""} />
            <Text type="secondary">Daily cap: {usage.data?.daily_limit || "unlimited"}</Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {tiles.map((tile) => (
          <Col xs={24} sm={12} lg={8} xl={6} key={tile.href}>
            <Link href={tile.href}>
              <Card hoverable>
                <Space align="start">
                  {tile.icon}
                  <Space direction="vertical" size={2}>
                    <Text strong>{tile.label}</Text>
                    <Text type="secondary">{tile.desc}</Text>
                  </Space>
                </Space>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <MoverTable title="Top gainers" rows={movers.data?.top_gainers ?? []} />
        </Col>
        <Col xs={24} lg={12}>
          <MoverTable title="Top losers" rows={movers.data?.top_losers ?? []} />
        </Col>
      </Row>
    </PageContainer>
  );
}

function MoverTable({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <Card title={title} size="small">
      <Table
        size="small"
        pagination={false}
        rowKey={(row) => String(row.ticker ?? row.symbol ?? JSON.stringify(row))}
        dataSource={rows.slice(0, 8)}
        columns={[
          { title: "Ticker", dataIndex: "ticker" },
          { title: "Price", dataIndex: "price" },
          { title: "Change", dataIndex: "change_amount" },
          { title: "Change %", dataIndex: "change_percentage" },
          { title: "Volume", dataIndex: "volume" },
        ]}
      />
    </Card>
  );
}
