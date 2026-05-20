import { LineChart, RefreshCcw } from "lucide-react";

import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

interface BacktestRun {
  id: string;
  run_name?: string;
  engine?: string;
  strategy?: string;
  status?: string;
  pnl_total?: number;
  sharpe?: number;
  max_drawdown?: number;
  win_rate?: number;
  started_at?: string;
}

export function BacktestRoute() {
  const runs = useApiQuery<{ items?: BacktestRun[] } | BacktestRun[]>({
    queryKey: ["backtest", "runs"],
    path: "/backtest/runs",
    refetchInterval: 10_000,
  });

  const list: BacktestRun[] = Array.isArray(runs.data)
    ? runs.data
    : Array.isArray(runs.data?.items)
      ? runs.data.items
      : [];

  return (
    <PageContainer
      title="Backtests"
      subtitle="Backtest runs (vbt-pro, event-driven, ZVT, AAT). Click a row for the detail view (Phase 2 follow-up)."
      extra={
        <Button variant="ghost" size="sm" onClick={() => runs.refetch()}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<BacktestRun>
            rows={list}
            rowKey={(r) => r.id}
            emptyState={
              <div className="flex flex-col items-center gap-2">
                <LineChart className="h-6 w-6" />
                <span>No backtests yet.</span>
              </div>
            }
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
                key: "engine",
                header: "Engine",
                width: 130,
                render: (r) => <Badge variant="secondary">{r.engine ?? "—"}</Badge>,
              },
              {
                key: "strategy",
                header: "Strategy",
                render: (r) => <span className="font-mono text-xs">{r.strategy ?? "—"}</span>,
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
                        : r.status === "running"
                          ? "default"
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
                key: "pnl_total",
                header: "Total PnL",
                width: 110,
                align: "right",
                render: (r) => <Numeric value={r.pnl_total ?? null} kind="money" digits={0} color="auto" signed />,
              },
              {
                key: "sharpe",
                header: "Sharpe",
                width: 90,
                align: "right",
                render: (r) => <Numeric value={r.sharpe ?? null} kind="decimal" digits={2} color="auto" />,
              },
              {
                key: "max_drawdown",
                header: "Max DD",
                width: 100,
                align: "right",
                render: (r) => (
                  <Numeric value={r.max_drawdown ?? null} kind="percent" digits={2} color="force-neg" />
                ),
              },
              {
                key: "win_rate",
                header: "Win",
                width: 90,
                align: "right",
                render: (r) => <Numeric value={r.win_rate ?? null} kind="percent" digits={1} color="auto" />,
              },
              {
                key: "started_at",
                header: "Started",
                width: 120,
                align: "right",
                render: (r) => (
                  <span className="text-[var(--text-secondary)]">
                    {r.started_at ? formatTime(r.started_at) : "—"}
                  </span>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
