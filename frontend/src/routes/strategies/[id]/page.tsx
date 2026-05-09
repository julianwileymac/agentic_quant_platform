import { ArrowLeft, FlaskConical, NotebookPen, RefreshCcw } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { CodeEditor } from "@/components/common/CodeEditor";
import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { strategiesApi, type StrategyDetail, type StrategyVersion } from "@/lib/api/strategies";
import type { BacktestRunSummary } from "@/lib/api/backtest";
import { formatTime } from "@/lib/utils";

export function StrategyDetailRoute() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);

  const detail = useApiQuery<StrategyDetail>({
    queryKey: ["strategies", id, "detail"],
    path: `/strategies/${encodeURIComponent(id ?? "")}`,
    enabled: Boolean(id),
  });
  const versions = useApiQuery<StrategyVersion[]>({
    queryKey: ["strategies", id, "versions"],
    path: `/strategies/${encodeURIComponent(id ?? "")}/versions`,
    enabled: Boolean(id),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const backtests = useApiQuery<BacktestRunSummary[]>({
    queryKey: ["strategies", id, "backtests"],
    path: "/backtest/runs",
    query: { strategy_id: id ?? "" },
    enabled: Boolean(id),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  if (!id) {
    return (
      <PageContainer title="Strategy" subtitle="Missing :id route param.">
        {null}
      </PageContainer>
    );
  }

  const data = detail.data;
  const metrics: Metric[] = [
    { label: "Sharpe (30d)", value: data?.last_sharpe ?? null, kind: "decimal", digits: 2 },
    { label: "Sortino (30d)", value: data?.last_sortino ?? null, kind: "decimal", digits: 2 },
    {
      label: "Max DD",
      value: data?.last_max_drawdown ?? null,
      kind: "percent",
      digits: 2,
      tone: "force-neg",
    },
    {
      label: "Versions",
      value: versions.data?.length ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
    },
  ];

  const submit = async () => {
    setBusy(true);
    try {
      const res = await strategiesApi.runBacktest(id);
      toast.success(`Backtest queued`, { description: `task_id=${res.task_id}` });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Run failed: ${msg}`);
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  };

  return (
    <PageContainer
      title={data?.name ?? "Strategy"}
      subtitle={
        <span className="font-mono text-xs">
          {id}
          {data?.class ? ` · ${data.class}` : ""}
        </span>
      }
      extra={
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate("/strategies")}>
            <ArrowLeft className="h-4 w-4" /> All strategies
          </Button>
          <Button variant="ghost" size="sm" onClick={() => detail.refetch()}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to={`/workflows/strategy?id=${encodeURIComponent(id)}`}>
              <NotebookPen className="h-4 w-4" /> Edit in composer
            </Link>
          </Button>
          <Button size="sm" onClick={() => setConfirm(true)} disabled={busy} className="gap-1">
            <FlaskConical className="h-4 w-4" /> Run backtest
          </Button>
        </div>
      }
    >
      <MetricsGrid metrics={metrics} columns={4} />

      <Tabs defaultValue="overview" className="mt-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="backtests">Backtests ({backtests.data?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="versions">Versions ({versions.data?.length ?? 0})</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Identity</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-[var(--text-secondary)]">Class</span>
                  <span className="font-mono">{data?.class ?? "—"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[var(--text-secondary)]">Module</span>
                  <span className="font-mono text-xs">{data?.module_path ?? "—"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[var(--text-secondary)]">Tags</span>
                  <div className="flex flex-wrap justify-end gap-1">
                    {(data?.tags ?? []).map((t) => (
                      <Badge key={t} variant="outline" className="text-[10px]">
                        {t}
                      </Badge>
                    ))}
                  </div>
                </div>
                {data?.description ? (
                  <p className="mt-2 text-xs text-[var(--text-secondary)]">{data.description}</p>
                ) : null}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Kwargs</CardTitle>
                <Badge variant="secondary">read-only</Badge>
              </CardHeader>
              <CardContent className="p-3">
                <div className="h-[300px]">
                  <CodeEditor
                    value={JSON.stringify(data?.kwargs ?? data?.config ?? {}, null, 2)}
                    language="json"
                    readOnly
                  />
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="backtests">
          <Card>
            <CardContent className="p-0">
              <div className="h-[60vh]">
                <DataTable<BacktestRunSummary>
                  rows={backtests.data ?? []}
                  rowKey={(r) => r.id}
                  onRowClick={(r) => navigate(`/backtest/${r.id}`)}
                  emptyState={<span>No backtests against this strategy yet.</span>}
                  columns={[
                    {
                      key: "name",
                      header: "Run",
                      render: (r) => (
                        <div className="flex flex-col">
                          <span className="font-medium">{r.run_name ?? r.id}</span>
                          <span className="font-mono text-[10px] text-[var(--text-muted)]">{r.id}</span>
                        </div>
                      ),
                    },
                    {
                      key: "status",
                      header: "Status",
                      width: 110,
                      render: (r) => (
                        <Badge
                          variant={
                            r.status === "completed"
                              ? "positive"
                              : r.status === "failed"
                                ? "negative"
                                : "secondary"
                          }
                        >
                          {r.status ?? "—"}
                        </Badge>
                      ),
                    },
                    {
                      key: "sharpe",
                      header: "Sharpe",
                      width: 90,
                      align: "right",
                      render: (r) => <Numeric value={r.sharpe ?? null} kind="decimal" digits={2} color="auto" />,
                    },
                    {
                      key: "max_dd",
                      header: "Max DD",
                      width: 100,
                      align: "right",
                      render: (r) => (
                        <Numeric value={r.max_drawdown ?? null} kind="percent" digits={2} color="force-neg" />
                      ),
                    },
                    {
                      key: "started_at",
                      header: "Started",
                      width: 130,
                      align: "right",
                      render: (r) => (
                        <span className="text-[var(--text-secondary)]">
                          {r.started_at ? formatTime(r.started_at) : "—"}
                        </span>
                      ),
                    },
                  ]}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="versions">
          <Card>
            <CardContent className="p-0">
              <div className="h-[60vh]">
                <DataTable<StrategyVersion>
                  rows={versions.data ?? []}
                  rowKey={(v) => v.id}
                  emptyState={<span>No versions persisted.</span>}
                  columns={[
                    {
                      key: "version",
                      header: "Version",
                      width: 100,
                      align: "right",
                      render: (v) => <Numeric value={v.version} kind="integer" digits={0} color="neutral" />,
                    },
                    {
                      key: "hash",
                      header: "Spec hash",
                      width: 200,
                      render: (v) => (
                        <span className="font-mono text-xs">{v.spec_hash.slice(0, 18)}…</span>
                      ),
                    },
                    {
                      key: "notes",
                      header: "Notes",
                      render: (v) => <span className="text-xs">{v.notes ?? "—"}</span>,
                    },
                    {
                      key: "created_at",
                      header: "Created",
                      width: 160,
                      align: "right",
                      render: (v) => (
                        <span className="text-[var(--text-secondary)]">{formatTime(v.created_at)}</span>
                      ),
                    },
                  ]}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {confirm ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(open) => !open && setConfirm(false)}
          title={`Run backtest — ${data?.name ?? id}`}
          consequence="Queues a backtest task against the latest strategy version. Reads from the configured Iceberg dataset; no live capital is at risk."
          details={[
            { label: "Strategy", value: data?.name ?? id },
            { label: "Class", value: data?.class ?? "—" },
            { label: "Module", value: data?.module_path ?? "—" },
          ]}
          confirmPhrase=""
          confirmLabel="Run backtest"
          confirmVariant="default"
          onConfirm={submit}
        />
      ) : null}
    </PageContainer>
  );
}
