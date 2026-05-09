import { Play, Sigma } from "lucide-react";
import { useEffect, useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { Heatmap, type HeatmapPoint } from "@/components/optimizer/Heatmap";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

interface OptimizerRun {
  id: string;
  strategy_class: string;
  metric: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at?: string;
  best_score?: number;
  results?: Array<{ params: Record<string, string | number>; metric: number }>;
}

const METRICS = ["sharpe", "max_drawdown", "total_return", "sortino"] as const;

export function OptimizerRoute() {
  const [strategyClass, setStrategyClass] = useState("MomentumStrategy");
  const [paramGrid, setParamGrid] = useState(
    JSON.stringify({ lookback: [10, 20, 30], threshold: [0.5, 1.0, 1.5] }, null, 2),
  );
  const [metric, setMetric] = useState<(typeof METRICS)[number]>("sharpe");
  const [pendingLaunch, setPendingLaunch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stub, setStub] = useState(false);

  const runs = useApiQuery<OptimizerRun[]>({
    queryKey: ["optimizer", "runs"],
    path: "/optimizer/runs",
    select: (raw) => (Array.isArray(raw) ? raw : []),
    retry: false,
  });

  useEffect(() => {
    if (runs.error instanceof ApiError && runs.error.status === 404) {
      setStub(true);
    }
  }, [runs.error]);

  const launch = async () => {
    let params: Record<string, unknown>;
    try {
      params = JSON.parse(paramGrid);
    } catch (err) {
      toast.error(`Invalid JSON: ${(err as Error).message}`);
      return;
    }
    setBusy(true);
    try {
      const res = await apiFetch<{ run_id: string }>("/optimizer/runs", {
        method: "POST",
        body: JSON.stringify({ strategy_class: strategyClass, param_grid: params, metric }),
      });
      toast.success(`Sweep ${res.run_id.slice(0, 8)} queued`);
      runs.refetch();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Launch failed: ${msg}`);
    } finally {
      setBusy(false);
      setPendingLaunch(false);
    }
  };

  const [selected, setSelected] = useState<OptimizerRun | null>(null);
  const heatmapPoints: HeatmapPoint[] = (selected?.results ?? [])
    .map((r) => {
      const ks = Object.keys(r.params);
      if (ks.length < 2) return null;
      const a = ks[0]!;
      const b = ks[1]!;
      return {
        paramA: r.params[a]!,
        paramB: r.params[b]!,
        metric: r.metric,
      };
    })
    .filter((p): p is HeatmapPoint => p !== null);

  const heatmapLabels = (() => {
    const sample = selected?.results?.[0]?.params;
    if (!sample) return { a: "param_a", b: "param_b" };
    const keys = Object.keys(sample);
    return { a: keys[0] ?? "param_a", b: keys[1] ?? "param_b" };
  })();

  const columns: ColumnDef<OptimizerRun>[] = [
    {
      key: "id",
      header: "Run",
      render: (r) => <span className="font-mono text-xs">{r.id.slice(0, 8)}</span>,
    },
    {
      key: "strategy",
      header: "Strategy",
      render: (r) => <span className="font-medium">{r.strategy_class}</span>,
    },
    {
      key: "metric",
      header: "Metric",
      width: 110,
      render: (r) => <Badge variant="secondary">{r.metric}</Badge>,
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
          {r.status}
        </Badge>
      ),
    },
    {
      key: "best_score",
      header: "Best",
      width: 110,
      align: "right",
      render: (r) => <Numeric value={r.best_score ?? null} kind="decimal" digits={3} color="auto" />,
    },
    {
      key: "created",
      header: "Created",
      width: 140,
      align: "right",
      render: (r) => (
        <span className="text-[var(--text-secondary)]">
          {r.created_at ? formatTime(r.created_at) : "—"}
        </span>
      ),
    },
  ];

  return (
    <PageContainer
      title="Optimizer"
      subtitle="Strategy parameter sweeps. Launch is friction-gated; recent sweeps and a (param_a × param_b) heatmap render below."
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[420px_1fr]">
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Launch sweep</CardTitle>
            {stub ? <Badge variant="warn">Pending API: POST /optimizer/runs</Badge> : null}
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="opt-class">Strategy class</Label>
              <Input
                id="opt-class"
                className="font-mono"
                value={strategyClass}
                onChange={(e) => setStrategyClass(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="opt-metric">Metric</Label>
              <select
                id="opt-metric"
                value={metric}
                onChange={(e) => setMetric(e.target.value as (typeof METRICS)[number])}
                className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
              >
                {METRICS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label>Param grid (JSON)</Label>
              <div className="h-48 overflow-hidden rounded-md">
                <CodeEditor language="json" value={paramGrid} onChange={setParamGrid} />
              </div>
              <p className="text-[10px] text-[var(--text-secondary)]">
                Cartesian product across keys. Values must be arrays.
              </p>
            </div>
            <Button
              variant="warn"
              onClick={() => setPendingLaunch(true)}
              disabled={busy || !strategyClass.trim()}
              className="gap-2"
            >
              <Play className="h-4 w-4" /> {busy ? "Launching…" : "Launch sweep"}
            </Button>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-3">
          <Card className="h-[40vh]">
            <CardHeader>
              <CardTitle>Recent sweeps</CardTitle>
              <Badge variant="secondary">{runs.data?.length ?? 0}</Badge>
            </CardHeader>
            <CardContent className="h-full p-0">
              <DataTable<OptimizerRun>
                rows={runs.data ?? []}
                rowKey={(r) => r.id}
                columns={columns}
                onRowClick={setSelected}
                emptyState={
                  stub ? (
                    <span>No optimizer endpoint registered.</span>
                  ) : runs.isPending ? (
                    <span>Loading…</span>
                  ) : (
                    <span>No sweeps yet.</span>
                  )
                }
              />
            </CardContent>
          </Card>
          <Card className="h-[40vh]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sigma className="h-4 w-4" />
                Heatmap
              </CardTitle>
              {selected ? (
                <span className="text-[10px] font-mono text-[var(--text-secondary)]">
                  {selected.id.slice(0, 8)}
                </span>
              ) : null}
            </CardHeader>
            <CardContent className="h-full p-3">
              <Heatmap
                points={heatmapPoints}
                paramALabel={heatmapLabels.a}
                paramBLabel={heatmapLabels.b}
                metricLabel={selected?.metric ?? metric}
              />
            </CardContent>
          </Card>
        </div>
      </div>

      {pendingLaunch ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(o) => !o && setPendingLaunch(false)}
          title={`Launch ${strategyClass} sweep`}
          consequence="Optimizer sweeps schedule a Celery task per cell of the cartesian product. A 4×4 grid is 16 backtests; a 10×10 grid is 100. Make sure your worker pool has the headroom."
          details={[
            { label: "Strategy", value: strategyClass },
            { label: "Metric", value: metric },
            {
              label: "Grid",
              value: paramGrid.replace(/\s+/g, " ").slice(0, 80) + (paramGrid.length > 80 ? "…" : ""),
            },
          ]}
          confirmPhrase="LAUNCH"
          confirmLabel="Launch sweep"
          confirmVariant="warn"
          onConfirm={launch}
        />
      ) : null}
    </PageContainer>
  );
}
