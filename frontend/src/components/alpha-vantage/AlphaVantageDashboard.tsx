import {
  BarChart3,
  Calendar,
  DollarSign,
  Globe2,
  LineChart,
  Settings as SettingsIcon,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { Link } from "react-router-dom";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";

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

const TILES = [
  { href: "/alpha-vantage/timeseries", label: "Time Series", icon: LineChart, desc: "Intraday, daily, weekly, monthly OHLCV" },
  { href: "/alpha-vantage/fundamentals", label: "Fundamentals", icon: Calendar, desc: "Overview, statements, earnings, corporate actions" },
  { href: "/alpha-vantage/technicals", label: "Technicals", icon: BarChart3, desc: "SMA, EMA, MACD, RSI and 50+ indicators" },
  { href: "/alpha-vantage/intelligence", label: "Intelligence", icon: Sparkles, desc: "News sentiment, movers, insider activity" },
  { href: "/alpha-vantage/forex", label: "Forex", icon: Globe2, desc: "FX rates and historical currency series" },
  { href: "/alpha-vantage/crypto", label: "Crypto", icon: DollarSign, desc: "Crypto rates and digital currency bars" },
  { href: "/alpha-vantage/options", label: "Options", icon: TrendingUp, desc: "Realtime and historical option chains" },
  { href: "/alpha-vantage/commodities", label: "Commodities", icon: BarChart3, desc: "Energy, metals, agriculture, global index" },
  { href: "/alpha-vantage/economics", label: "Economics", icon: Calendar, desc: "GDP, CPI, treasury yields, federal funds" },
  { href: "/alpha-vantage/indices", label: "Indices", icon: LineChart, desc: "Index series and catalog endpoints" },
  { href: "/alpha-vantage/admin", label: "Admin", icon: SettingsIcon, desc: "Bulk-load jobs and provider controls" },
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

  const metrics: Metric[] = [
    {
      label: "Provider",
      value: null,
      hint: (
        <span className="flex items-center gap-1">
          <Badge variant={health.data?.enabled ? "positive" : "secondary"}>
            {health.data?.enabled ? "enabled" : "disabled"}
          </Badge>
          <Badge variant={health.data?.credentials_loaded ? "positive" : "warn"}>
            {health.data?.credentials_loaded ? "key loaded" : "no key"}
          </Badge>
        </span>
      ),
    },
    {
      label: "Requests this minute",
      value: usage.data?.requests_this_minute ?? 0,
      kind: "integer",
      digits: 0,
      tone: "neutral",
      hint: <span>/ {usage.data?.rpm_limit ?? health.data?.rpm_limit ?? "?"} rpm</span>,
    },
    {
      label: "Requests today",
      value: usage.data?.requests_today ?? 0,
      kind: "integer",
      digits: 0,
      tone: "neutral",
      hint: usage.data?.daily_limit ? <span>/ {usage.data.daily_limit} daily</span> : <span>unlimited</span>,
    },
  ];

  return (
    <PageContainer
      title="Alpha Vantage"
      subtitle="Primary market-data provider for quotes, fundamentals, news, options, FX, crypto, commodities, economics, and technical indicators."
    >
      {health.data && !health.data.credentials_loaded ? (
        <Card className="mb-3 border-[var(--warn-fg)]">
          <CardContent className="py-3 text-sm">
            <Badge variant="warn">credentials missing</Badge>
            <span className="ml-2">
              Set <code className="font-mono">AQP_ALPHA_VANTAGE_API_KEY</code> or{" "}
              <code className="font-mono">AQP_ALPHA_VANTAGE_API_KEY_FILE</code> to enable live provider calls.
            </span>
          </CardContent>
        </Card>
      ) : null}

      <MetricsGrid metrics={metrics} columns={3} />

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {TILES.map((tile) => {
          const Icon = tile.icon;
          return (
            <Link key={tile.href} to={tile.href} className="block">
              <Card className="h-full transition-colors hover:border-[var(--info-fg)]">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Icon className="h-4 w-4" />
                    {tile.label}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-[var(--text-secondary)]">{tile.desc}</p>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <MoverTable title="Top gainers" rows={movers.data?.top_gainers ?? []} loading={movers.isPending} />
        <MoverTable title="Top losers" rows={movers.data?.top_losers ?? []} loading={movers.isPending} />
      </div>
    </PageContainer>
  );
}

function MoverTable({
  title,
  rows,
  loading,
}: {
  title: string;
  rows: Array<Record<string, unknown>>;
  loading: boolean;
}) {
  const columns: ColumnDef<Record<string, unknown>>[] = [
    { key: "ticker", header: "Ticker", render: (r) => <span className="font-mono">{String(r.ticker ?? r.symbol ?? "?")}</span> },
    { key: "price", header: "Price", align: "right", render: (r) => <span className="font-mono">{String(r.price ?? "")}</span> },
    {
      key: "change_amount",
      header: "Change",
      align: "right",
      render: (r) => <span className="font-mono">{String(r.change_amount ?? "")}</span>,
    },
    {
      key: "change_percentage",
      header: "Change %",
      align: "right",
      render: (r) => <span className="font-mono">{String(r.change_percentage ?? "")}</span>,
    },
    { key: "volume", header: "Volume", align: "right", render: (r) => <span className="font-mono">{String(r.volume ?? "")}</span> },
  ];
  return (
    <Card className="h-[280px]">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="h-full p-0">
        <DataTable<Record<string, unknown>>
          rows={rows.slice(0, 8)}
          rowKey={(r, i) => String(r.ticker ?? r.symbol ?? i)}
          columns={columns}
          emptyState={loading ? <span>Loading…</span> : <span>No data.</span>}
        />
      </CardContent>
    </Card>
  );
}
