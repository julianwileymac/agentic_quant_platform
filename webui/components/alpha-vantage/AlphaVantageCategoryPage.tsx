"use client";

import { App, Button, Card, Form, Input, Select, Space, Table, Typography } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";

const { Text } = Typography;

type CategoryKind =
  | "timeseries"
  | "fundamentals"
  | "technicals"
  | "intelligence"
  | "forex"
  | "crypto"
  | "options"
  | "commodities"
  | "economics"
  | "indices";

interface CategoryPageProps {
  kind: CategoryKind;
}

interface QueryForm {
  symbol?: string;
  function?: string;
  interval?: string;
  kind?: string;
  indicator?: string;
  from?: string;
  to?: string;
  market?: string;
}

interface FieldSpec {
  name: string;
  label: string;
  required?: boolean;
  placeholder?: string;
  options?: string[];
  width?: number;
}

const copy: Record<CategoryKind, { title: string; subtitle: string }> = {
  timeseries: { title: "Alpha Vantage Time Series", subtitle: "Fetch OHLCV bars and quote snapshots." },
  fundamentals: { title: "Alpha Vantage Fundamentals", subtitle: "Company overview, financial statements, earnings, dividends, and listings." },
  technicals: { title: "Alpha Vantage Technicals", subtitle: "Request technical indicators for a ticker and interval." },
  intelligence: { title: "Alpha Vantage Intelligence", subtitle: "News sentiment, top movers, transcripts, insider and institutional activity." },
  forex: { title: "Alpha Vantage Forex", subtitle: "Currency rates and historical FX series." },
  crypto: { title: "Alpha Vantage Crypto", subtitle: "Digital currency rates and historical bars." },
  options: { title: "Alpha Vantage Options", subtitle: "Realtime and historical option chain endpoints." },
  commodities: { title: "Alpha Vantage Commodities", subtitle: "Energy, metals, agriculture, and commodity index series." },
  economics: { title: "Alpha Vantage Economics", subtitle: "GDP, CPI, treasury yields, federal funds rate, and macro series." },
  indices: { title: "Alpha Vantage Indices", subtitle: "Index catalog and series endpoints." },
};

export function AlphaVantageCategoryPage({ kind }: CategoryPageProps) {
  const { message } = App.useApp();
  const [form] = Form.useForm<QueryForm>();
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState<unknown>(null);

  async function submit() {
    const values = await form.validateFields();
    setLoading(true);
    try {
      const result = await apiFetch<unknown>(pathFor(kind, values), { query: queryFor(kind, values) });
      setPayload(result);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageContainer title={copy[kind].title} subtitle={copy[kind].subtitle}>
      <Card size="small" title="Request">
        <Form<QueryForm>
          form={form}
          layout="vertical"
          initialValues={defaultsFor(kind)}
          onFinish={submit}
        >
          <Space wrap align="end">
            {fieldsFor(kind).map((field) => (
              <Form.Item
                key={field.name}
                label={field.label}
                name={field.name}
                rules={field.required ? [{ required: true, message: "Required" }] : undefined}
                style={{ minWidth: field.width ?? 180 }}
              >
                {field.options ? (
                  <Select options={field.options.map((value) => ({ value, label: value }))} />
                ) : (
                  <Input placeholder={field.placeholder} />
                )}
              </Form.Item>
            ))}
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading}>
                Fetch
              </Button>
            </Form.Item>
          </Space>
        </Form>
      </Card>

      <Card size="small" title="Result" style={{ marginTop: 16 }}>
        {Array.isArray(normalizedRows(payload)) ? (
          <Table
            size="small"
            rowKey={(_, index) => String(index)}
            dataSource={normalizedRows(payload)}
            columns={columnsFor(normalizedRows(payload))}
            scroll={{ x: true }}
          />
        ) : (
          <Text type="secondary">Run a request to view data.</Text>
        )}
      </Card>
    </PageContainer>
  );
}

function pathFor(kind: CategoryKind, values: QueryForm) {
  if (kind === "timeseries") return `/alpha-vantage/timeseries/${values.function}`;
  if (kind === "fundamentals") return `/alpha-vantage/fundamentals/${values.kind}`;
  if (kind === "technicals") return `/alpha-vantage/technicals/${values.indicator}`;
  if (kind === "intelligence") return `/alpha-vantage/intelligence/${values.kind}`;
  if (kind === "forex") return `/alpha-vantage/forex/${values.kind}`;
  if (kind === "crypto") return `/alpha-vantage/crypto/${values.kind}`;
  if (kind === "options") return `/alpha-vantage/options/${values.kind}`;
  if (kind === "commodities") return `/alpha-vantage/commodities/${values.kind}`;
  if (kind === "economics") return `/alpha-vantage/economics/${values.kind}`;
  if (kind === "indices" && values.kind === "catalog") return "/alpha-vantage/indices/catalog";
  return `/alpha-vantage/indices/${values.kind}`;
}

function queryFor(kind: CategoryKind, values: QueryForm) {
  if (kind === "forex") return { from: values.from, to: values.to, interval: values.interval };
  return {
    symbol: values.symbol,
    interval: values.interval,
    market: values.market,
    series_type: "close",
  };
}

function defaultsFor(kind: CategoryKind): QueryForm {
  const common = { symbol: "IBM", interval: "daily" };
  if (kind === "timeseries") return { ...common, function: "daily" };
  if (kind === "fundamentals") return { ...common, kind: "overview" };
  if (kind === "technicals") return { ...common, indicator: "SMA" };
  if (kind === "intelligence") return { ...common, kind: "news" };
  if (kind === "forex") return { kind: "rate", from: "USD", to: "JPY", interval: "daily" };
  if (kind === "crypto") return { kind: "rate", symbol: "BTC", market: "USD", interval: "daily" };
  if (kind === "options") return { kind: "realtime", symbol: "IBM" };
  if (kind === "commodities") return { kind: "WTI", interval: "monthly" };
  if (kind === "economics") return { kind: "REAL_GDP", interval: "annual" };
  return { kind: "catalog" };
}

function fieldsFor(kind: CategoryKind): FieldSpec[] {
  const symbol = { name: "symbol", label: "Symbol", required: true, placeholder: "IBM" };
  const interval = { name: "interval", label: "Interval", placeholder: "daily" };
  if (kind === "timeseries") {
    return [
      symbol,
      { name: "function", label: "Function", required: true, options: ["intraday", "daily", "daily_adjusted", "weekly", "monthly", "global_quote"] },
      interval,
    ];
  }
  if (kind === "fundamentals") {
    return [symbol, { name: "kind", label: "Kind", required: true, options: ["overview", "income", "balance", "cashflow", "earnings", "dividends", "splits", "listing"] }];
  }
  if (kind === "technicals") return [symbol, { name: "indicator", label: "Indicator", required: true, placeholder: "SMA" }, interval];
  if (kind === "intelligence") return [symbol, { name: "kind", label: "Kind", required: true, options: ["news", "top-movers", "insider", "institutional"] }];
  if (kind === "forex") return [{ name: "kind", label: "Kind", required: true, options: ["rate", "daily", "weekly", "monthly"] }, { name: "from", label: "From", required: true }, { name: "to", label: "To", required: true }, interval];
  if (kind === "crypto") return [{ name: "kind", label: "Kind", required: true, options: ["rate", "daily", "weekly", "monthly"] }, symbol, { name: "market", label: "Market", required: true }, interval];
  if (kind === "options") return [symbol, { name: "kind", label: "Kind", required: true, options: ["realtime", "historical", "pcr-realtime", "voi-realtime"] }];
  if (kind === "commodities") return [{ name: "kind", label: "Commodity", required: true, placeholder: "WTI" }, interval];
  if (kind === "economics") return [{ name: "kind", label: "Indicator", required: true, placeholder: "REAL_GDP" }, interval];
  return [{ name: "kind", label: "Index", required: true, options: ["catalog", "MARKET_STATUS"] }];
}

function normalizedRows(payload: unknown): Array<Record<string, unknown>> {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload.filter(isRecord);
  if (isRecord(payload)) {
    if (Array.isArray(payload.bars)) return payload.bars.filter(isRecord);
    if (Array.isArray(payload.feed)) return payload.feed.filter(isRecord);
    if (Array.isArray(payload.markets)) return payload.markets.filter(isRecord);
    if (Array.isArray(payload.annual)) return payload.annual.filter(isRecord);
    if (Array.isArray(payload.data)) return payload.data.filter(isRecord);
    return [payload];
  }
  return [{ value: String(payload) }];
}

function columnsFor(rows: Array<Record<string, unknown>>) {
  const sample = rows[0] ?? {};
  return Object.keys(sample).slice(0, 12).map((key) => ({
    title: key,
    dataIndex: key,
    render: (value: unknown) => (typeof value === "object" ? JSON.stringify(value) : String(value ?? "")),
  }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
