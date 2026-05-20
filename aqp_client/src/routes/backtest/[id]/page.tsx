import { ArrowLeft, ListVideo, RefreshCcw } from "lucide-react";
import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { EquityChart } from "@/components/charts/EquityChart";
import { DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import {
  type BacktestRunDetail,
  type BacktestTrade,
  type PlotResponse,
  plotToSeries,
} from "@/lib/api/backtest";
import { formatTime } from "@/lib/utils";

export function BacktestDetailRoute() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const detail = useApiQuery<BacktestRunDetail>({
    queryKey: ["backtest", id, "detail"],
    path: `/backtest/runs/${encodeURIComponent(id ?? "")}`,
    enabled: Boolean(id),
    refetchInterval: (q) => {
      const status = (q.state.data as BacktestRunDetail | undefined)?.status;
      return status === "running" || status === "queued" ? 4_000 : false;
    },
  });
  const equityPlot = useApiQuery<PlotResponse>({
    queryKey: ["backtest", id, "equity"],
    path: `/backtest/runs/${encodeURIComponent(id ?? "")}/plot/equity`,
    enabled: Boolean(id),
  });
  const drawdownPlot = useApiQuery<PlotResponse>({
    queryKey: ["backtest", id, "drawdown"],
    path: `/backtest/runs/${encodeURIComponent(id ?? "")}/plot/drawdown`,
    enabled: Boolean(id),
  });
  const trades = useApiQuery<BacktestTrade[]>({
    queryKey: ["backtest", id, "trades"],
    path: `/backtest/runs/${encodeURIComponent(id ?? "")}/trades`,
    enabled: Boolean(id),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const equity = useMemo(() => plotToSeries(equityPlot.data), [equityPlot.data]);
  const drawdown = useMemo(() => plotToSeries(drawdownPlot.data), [drawdownPlot.data]);
  const data = detail.data;

  const metrics: Metric[] = [
    {
      label: "Status",
      value: null,
      hint: (
        <Badge
          variant={
            data?.status === "completed"
              ? "positive"
              : data?.status === "failed"
                ? "negative"
                : data?.status === "running"
                  ? "default"
                  : "secondary"
          }
        >
          {data?.status ?? "—"}
        </Badge>
      ),
    },
    { label: "Total return", value: data?.total_return ?? null, kind: "percent", digits: 2, signed: true },
    { label: "Sharpe", value: data?.sharpe ?? null, kind: "decimal", digits: 2 },
    { label: "Sortino", value: data?.sortino ?? null, kind: "decimal", digits: 2 },
    { label: "Calmar", value: data?.calmar ?? null, kind: "decimal", digits: 2 },
    { label: "Max DD", value: data?.max_drawdown ?? null, kind: "percent", digits: 2, tone: "force-neg" },
    { label: "Win rate", value: data?.win_rate ?? null, kind: "percent", digits: 1 },
    { label: "Profit factor", value: data?.profit_factor ?? null, kind: "decimal", digits: 2 },
  ];

  if (!id) {
    return <PageContainer title="Backtest" subtitle="Missing :id route param.">{null}</PageContainer>;
  }

  return (
    <PageContainer
      title={data?.run_name ?? "Backtest run"}
      subtitle={
        <span className="font-mono text-xs">
          {id}
          {data?.engine ? ` · ${data.engine}` : ""}
          {data?.dataset_hash ? ` · dataset ${data.dataset_hash.slice(0, 12)}` : ""}
        </span>
      }
      extra={
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate("/backtest")}>
            <ArrowLeft className="h-4 w-4" /> All runs
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              detail.refetch();
              equityPlot.refetch();
              drawdownPlot.refetch();
              trades.refetch();
            }}
          >
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button variant="outline" size="sm" disabled>
            <ListVideo className="h-4 w-4" /> Replay (Phase 4)
          </Button>
        </div>
      }
      bleed
    >
      <div className="flex h-full flex-col gap-3 px-6 pb-6">
        <MetricsGrid metrics={metrics} columns={4} />

        <PanelGroup direction="horizontal" className="flex flex-1 gap-2">
          <Panel defaultSize={70} minSize={45}>
            <PanelGroup direction="vertical" className="flex h-full flex-col gap-2">
              <Panel defaultSize={60} minSize={30}>
                <Card className="flex h-full flex-col">
                  <CardHeader>
                    <CardTitle>Equity curve</CardTitle>
                    <Badge variant="secondary">D3</Badge>
                  </CardHeader>
                  <CardContent className="flex-1 p-3">
                    <EquityChart data={equity} height={320} showDrawdown />
                  </CardContent>
                </Card>
              </Panel>
              <PanelResizeHandle className="h-1 cursor-row-resize bg-[var(--border-default)]" />
              <Panel defaultSize={40} minSize={20}>
                <Card className="flex h-full flex-col">
                  <CardHeader>
                    <CardTitle>Trades ({trades.data?.length ?? 0})</CardTitle>
                  </CardHeader>
                  <CardContent className="flex-1 p-0">
                    <DataTable<BacktestTrade>
                      rows={trades.data ?? []}
                      rowKey={(t, i) => `${t.ts ?? "_"}-${t.vt_symbol ?? "_"}-${i}`}
                      emptyState={<span>No trades.</span>}
                      columns={[
                        {
                          key: "ts",
                          header: "Time",
                          width: 130,
                          render: (t) => (
                            <span className="text-[var(--text-secondary)]">{t.ts ? formatTime(t.ts) : "—"}</span>
                          ),
                        },
                        {
                          key: "vt_symbol",
                          header: "Symbol",
                          width: 130,
                          render: (t) => <span className="font-mono text-xs">{t.vt_symbol ?? "—"}</span>,
                        },
                        {
                          key: "side",
                          header: "Side",
                          width: 80,
                          render: (t) => (
                            <Badge variant={t.side === "buy" ? "positive" : "negative"}>{t.side ?? "—"}</Badge>
                          ),
                        },
                        {
                          key: "qty",
                          header: "Qty",
                          width: 90,
                          align: "right",
                          render: (t) => <Numeric value={t.qty ?? null} kind="integer" digits={0} color="auto" signed />,
                        },
                        {
                          key: "price",
                          header: "Price",
                          width: 110,
                          align: "right",
                          render: (t) => <Numeric value={t.price ?? null} kind="decimal" digits={2} color="neutral" />,
                        },
                        {
                          key: "pnl",
                          header: "PnL",
                          width: 110,
                          align: "right",
                          render: (t) => <Numeric value={t.pnl ?? null} kind="money" digits={0} color="auto" signed />,
                        },
                      ]}
                    />
                  </CardContent>
                </Card>
              </Panel>
            </PanelGroup>
          </Panel>
          <PanelResizeHandle className="w-1 cursor-col-resize bg-[var(--border-default)]" />
          <Panel defaultSize={30} minSize={22}>
            <Card className="flex h-full flex-col">
              <CardHeader>
                <CardTitle>Drawdown</CardTitle>
              </CardHeader>
              <CardContent className="flex-1 p-3">
                <EquityChart data={drawdown} height={200} zeroBased showDrawdown={false} />
              </CardContent>
              <CardContent className="border-t border-[var(--border-subtle)] text-xs text-[var(--text-secondary)]">
                <p>
                  Underlying run row in{" "}
                  <code className="rounded bg-[var(--bg-app)] px-1 font-mono">backtest_runs</code>.
                  Replay against{" "}
                  <Link className="text-[var(--info-fg)] underline" to={`/backtest/${id}/replay`}>
                    /backtest/{id}/replay
                  </Link>{" "}
                  lands in Phase 4 alongside the visual JudgeReport viewer.
                </p>
              </CardContent>
            </Card>
          </Panel>
        </PanelGroup>
      </div>
    </PageContainer>
  );
}
