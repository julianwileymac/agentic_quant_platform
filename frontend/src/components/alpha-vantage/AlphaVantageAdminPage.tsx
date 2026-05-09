import { CloudDownload, Loader2, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

interface HealthPayload {
  enabled: boolean;
  credentials_loaded: boolean;
  base_url: string;
  rpm_limit: number;
  daily_limit: number;
  cache_backend: string;
  message?: string | null;
}

interface AlphaVantageFunction {
  id: string;
  label: string;
  category: string;
  function: string;
  domain: string;
  iceberg_table?: string | null;
  iceberg_identifier?: string | null;
  lake_supported?: boolean;
}

interface FunctionsResponse {
  functions: AlphaVantageFunction[];
}

interface QueueResponse {
  task_id: string;
  stream_url: string;
}

export function AlphaVantageAdminPage() {
  const health = useApiQuery<HealthPayload>({
    queryKey: ["alpha-vantage", "health", "admin"],
    path: "/alpha-vantage/health",
    refetchInterval: 60_000,
  });
  const fns = useApiQuery<FunctionsResponse>({
    queryKey: ["alpha-vantage", "functions"],
    path: "/alpha-vantage/functions",
    staleTime: 5 * 60 * 1000,
  });

  const lakeFunctions = useMemo(
    () => (fns.data?.functions ?? []).filter((f) => f.lake_supported),
    [fns.data],
  );

  const [selected, setSelected] = useState<string[]>(["timeseries.daily_adjusted"]);
  const [exchangeFilter, setExchangeFilter] = useState("");
  const [limit, setLimit] = useState<string>("50");
  const [busy, setBusy] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);

  const queueAll = async () => {
    if (selected.length === 0) {
      toast.warning("Pick at least one endpoint");
      return;
    }
    setBusy(true);
    try {
      const exchanges = exchangeFilter
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await apiFetch<QueueResponse>("/pipelines/alpha-vantage/endpoints", {
        method: "POST",
        body: JSON.stringify({
          endpoints: selected,
          symbols: "all_active",
          filters: exchanges.length > 0 ? { exchange: exchanges } : {},
          limit: limit ? Number(limit) : null,
          cache: true,
        }),
      });
      setTaskId(res.task_id);
      toast.success(`Bulk load queued: ${res.task_id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

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
    { label: "Rate limit (rpm)", value: health.data?.rpm_limit ?? null, kind: "integer", digits: 0, tone: "neutral" },
    {
      label: "Daily limit",
      value: health.data?.daily_limit ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
      hint: !health.data?.daily_limit ? <span>unlimited</span> : undefined,
    },
    {
      label: "Cache",
      value: null,
      hint: <span className="font-mono text-xs">{health.data?.cache_backend ?? "—"}</span>,
    },
  ];

  const fnColumns: ColumnDef<AlphaVantageFunction>[] = [
    { key: "label", header: "Function", render: (r) => <span className="font-medium">{r.label}</span> },
    { key: "category", header: "Category", width: 130, render: (r) => <Badge variant="secondary">{r.category}</Badge> },
    {
      key: "iceberg_identifier",
      header: "Iceberg table",
      render: (r) => <span className="font-mono text-xs">{r.iceberg_identifier ?? "—"}</span>,
    },
    {
      key: "lake",
      header: "Lake",
      width: 90,
      render: (r) => (
        <Badge variant={r.lake_supported ? "positive" : "secondary"}>
          {r.lake_supported ? "yes" : "no"}
        </Badge>
      ),
    },
  ];

  return (
    <PageContainer
      title="Alpha Vantage Admin"
      subtitle="Provider health, rate-limit posture, and Celery-backed bulk loads into the per-endpoint Iceberg lake."
      extra={
        <Button variant="ghost" size="sm" onClick={() => fns.refetch()} className="gap-1">
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <MetricsGrid metrics={metrics} columns={4} />

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-[420px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CloudDownload className="h-4 w-4" /> Bulk loader
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="endpoints">Endpoints (multi-select)</Label>
              <select
                id="endpoints"
                multiple
                value={selected}
                onChange={(e) =>
                  setSelected(Array.from(e.target.selectedOptions).map((o) => o.value))
                }
                className="h-40 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-2 py-1 font-mono text-xs"
              >
                {lakeFunctions.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.label} ({f.iceberg_identifier ?? f.function})
                  </option>
                ))}
              </select>
              <p className="text-[10px] text-[var(--text-secondary)]">
                Hold Ctrl / Cmd to multi-select. Only lake-supported functions are listed.
              </p>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="exchanges">Exchange filter (comma-separated)</Label>
              <Input
                id="exchanges"
                placeholder="NASDAQ, NYSE"
                value={exchangeFilter}
                onChange={(e) => setExchangeFilter(e.target.value)}
                className="font-mono"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="limit">Symbol cap (optional)</Label>
              <Input
                id="limit"
                type="number"
                min={1}
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                className="font-mono"
              />
            </div>
            <Button onClick={queueAll} disabled={busy} className="gap-2">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
              {busy ? "Queueing…" : "Queue bulk load"}
            </Button>
            {taskId ? (
              <p className="text-xs text-[var(--text-secondary)]">
                Task <code className="font-mono">{taskId}</code> queued. Track progress via{" "}
                <code className="font-mono">/chat/stream/{taskId}</code>.
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card className="h-[55vh]">
          <CardHeader>
            <CardTitle>Lake-supported functions</CardTitle>
            <Badge variant="secondary">{lakeFunctions.length}</Badge>
          </CardHeader>
          <CardContent className="h-full p-0">
            <DataTable<AlphaVantageFunction>
              rows={lakeFunctions}
              rowKey={(r) => r.id}
              columns={fnColumns}
              emptyState={
                fns.isPending ? <span>Loading…</span> : <span>No lake-backed functions registered.</span>
              }
            />
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
