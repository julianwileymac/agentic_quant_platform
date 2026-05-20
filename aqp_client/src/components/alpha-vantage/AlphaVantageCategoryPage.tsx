import { Play } from "lucide-react";
import { useState } from "react";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

export type AlphaVantageCategory =
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
  kind: AlphaVantageCategory;
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
  name: keyof QueryForm;
  label: string;
  required?: boolean;
  placeholder?: string;
  options?: string[];
}

const COPY: Record<AlphaVantageCategory, { title: string; subtitle: string }> = {
  timeseries: { title: "Alpha Vantage Time Series", subtitle: "Fetch OHLCV bars and quote snapshots." },
  fundamentals: {
    title: "Alpha Vantage Fundamentals",
    subtitle: "Company overview, financial statements, earnings, dividends, and listings.",
  },
  technicals: { title: "Alpha Vantage Technicals", subtitle: "Request technical indicators for a ticker and interval." },
  intelligence: {
    title: "Alpha Vantage Intelligence",
    subtitle: "News sentiment, top movers, transcripts, insider and institutional activity.",
  },
  forex: { title: "Alpha Vantage Forex", subtitle: "Currency rates and historical FX series." },
  crypto: { title: "Alpha Vantage Crypto", subtitle: "Digital currency rates and historical bars." },
  options: { title: "Alpha Vantage Options", subtitle: "Realtime and historical option chain endpoints." },
  commodities: {
    title: "Alpha Vantage Commodities",
    subtitle: "Energy, metals, agriculture, and commodity index series.",
  },
  economics: {
    title: "Alpha Vantage Economics",
    subtitle: "GDP, CPI, treasury yields, federal funds rate, and macro series.",
  },
  indices: { title: "Alpha Vantage Indices", subtitle: "Index catalog and series endpoints." },
};

export function AlphaVantageCategoryPage({ kind }: CategoryPageProps) {
  const [form, setForm] = useState<QueryForm>(defaultsFor(kind));
  const [busy, setBusy] = useState(false);
  const [payload, setPayload] = useState<unknown>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const result = await apiFetch<unknown>(pathFor(kind, form), { query: queryFor(kind, form) });
      setPayload(result);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const rows = normalizedRows(payload);
  const columns = columnsFor(rows);

  const setField = (k: keyof QueryForm, v: string) => setForm((prev) => ({ ...prev, [k]: v }));

  return (
    <PageContainer title={COPY[kind].title} subtitle={COPY[kind].subtitle}>
      <Card className="mb-3">
        <CardHeader>
          <CardTitle>Request</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            {fieldsFor(kind).map((field) => (
              <div key={field.name} className="flex min-w-[180px] flex-col gap-1">
                <Label htmlFor={field.name}>
                  {field.label}
                  {field.required ? <span className="ml-1 text-[var(--neg-fg)]">*</span> : null}
                </Label>
                {field.options ? (
                  <select
                    id={field.name}
                    required={field.required}
                    value={String(form[field.name] ?? "")}
                    onChange={(e) => setField(field.name, e.target.value)}
                    className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm font-mono"
                  >
                    {field.options.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input
                    id={field.name}
                    required={field.required}
                    placeholder={field.placeholder ?? ""}
                    value={String(form[field.name] ?? "")}
                    onChange={(e) => setField(field.name, e.target.value)}
                    className="font-mono"
                  />
                )}
              </div>
            ))}
            <Button type="submit" disabled={busy} className="gap-2">
              <Play className="h-4 w-4" /> {busy ? "Fetching…" : "Fetch"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="h-[60vh]">
        <CardHeader>
          <CardTitle>Result</CardTitle>
        </CardHeader>
        <CardContent className="h-full p-0">
          {rows.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-[var(--text-secondary)]">
              {payload == null ? "Run a request to view data." : "No tabular data in payload."}
            </div>
          ) : (
            <DataTable<Record<string, unknown>>
              rows={rows}
              rowKey={(_, i) => String(i)}
              columns={columns}
            />
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}

function pathFor(kind: AlphaVantageCategory, values: QueryForm) {
  if (kind === "timeseries") return `/alpha-vantage/timeseries/${values.function ?? "daily"}`;
  if (kind === "fundamentals") return `/alpha-vantage/fundamentals/${values.kind ?? "overview"}`;
  if (kind === "technicals") return `/alpha-vantage/technicals/${values.indicator ?? "SMA"}`;
  if (kind === "intelligence") return `/alpha-vantage/intelligence/${values.kind ?? "news"}`;
  if (kind === "forex") return `/alpha-vantage/forex/${values.kind ?? "rate"}`;
  if (kind === "crypto") return `/alpha-vantage/crypto/${values.kind ?? "rate"}`;
  if (kind === "options") return `/alpha-vantage/options/${values.kind ?? "realtime"}`;
  if (kind === "commodities") return `/alpha-vantage/commodities/${values.kind ?? "WTI"}`;
  if (kind === "economics") return `/alpha-vantage/economics/${values.kind ?? "REAL_GDP"}`;
  if (kind === "indices" && values.kind === "catalog") return "/alpha-vantage/indices/catalog";
  return `/alpha-vantage/indices/${values.kind ?? "catalog"}`;
}

function queryFor(kind: AlphaVantageCategory, values: QueryForm): Record<string, string | undefined> {
  if (kind === "forex") {
    return {
      ...(values.from ? { from: values.from } : {}),
      ...(values.to ? { to: values.to } : {}),
      ...(values.interval ? { interval: values.interval } : {}),
    };
  }
  return {
    ...(values.symbol ? { symbol: values.symbol } : {}),
    ...(values.interval ? { interval: values.interval } : {}),
    ...(values.market ? { market: values.market } : {}),
    series_type: "close",
  };
}

function defaultsFor(kind: AlphaVantageCategory): QueryForm {
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

function fieldsFor(kind: AlphaVantageCategory): FieldSpec[] {
  const symbol: FieldSpec = { name: "symbol", label: "Symbol", required: true, placeholder: "IBM" };
  const interval: FieldSpec = { name: "interval", label: "Interval", placeholder: "daily" };
  if (kind === "timeseries") {
    return [
      symbol,
      {
        name: "function",
        label: "Function",
        required: true,
        options: ["intraday", "daily", "daily_adjusted", "weekly", "monthly", "global_quote"],
      },
      interval,
    ];
  }
  if (kind === "fundamentals") {
    return [
      symbol,
      {
        name: "kind",
        label: "Kind",
        required: true,
        options: ["overview", "income", "balance", "cashflow", "earnings", "dividends", "splits", "listing"],
      },
    ];
  }
  if (kind === "technicals") {
    return [symbol, { name: "indicator", label: "Indicator", required: true, placeholder: "SMA" }, interval];
  }
  if (kind === "intelligence") {
    return [
      symbol,
      { name: "kind", label: "Kind", required: true, options: ["news", "top-movers", "insider", "institutional"] },
    ];
  }
  if (kind === "forex") {
    return [
      { name: "kind", label: "Kind", required: true, options: ["rate", "daily", "weekly", "monthly"] },
      { name: "from", label: "From", required: true },
      { name: "to", label: "To", required: true },
      interval,
    ];
  }
  if (kind === "crypto") {
    return [
      { name: "kind", label: "Kind", required: true, options: ["rate", "daily", "weekly", "monthly"] },
      symbol,
      { name: "market", label: "Market", required: true },
      interval,
    ];
  }
  if (kind === "options") {
    return [
      symbol,
      {
        name: "kind",
        label: "Kind",
        required: true,
        options: ["realtime", "historical", "pcr-realtime", "voi-realtime"],
      },
    ];
  }
  if (kind === "commodities")
    return [{ name: "kind", label: "Commodity", required: true, placeholder: "WTI" }, interval];
  if (kind === "economics")
    return [{ name: "kind", label: "Indicator", required: true, placeholder: "REAL_GDP" }, interval];
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

function columnsFor(rows: Array<Record<string, unknown>>): ColumnDef<Record<string, unknown>>[] {
  const sample = rows[0] ?? {};
  return Object.keys(sample)
    .slice(0, 12)
    .map((key) => ({
      key,
      header: key,
      render: (row: Record<string, unknown>) => {
        const v = row[key];
        return (
          <span className="font-mono text-xs">
            {typeof v === "object" ? JSON.stringify(v) : String(v ?? "")}
          </span>
        );
      },
    }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
