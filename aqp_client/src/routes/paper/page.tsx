import { Pause, Play, RefreshCcw } from "lucide-react";
import { useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

interface PaperRun {
  id: string;
  task_id?: string | null;
  run_name?: string;
  status?: string;
  initial_cash?: number;
  cash?: number;
  equity?: number;
  pnl_session?: number;
  started_at?: string;
}

export function PaperRoute() {
  const runs = useApiQuery<PaperRun[]>({
    queryKey: ["paper", "runs"],
    path: "/paper/runs",
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const [target, setTarget] = useState<PaperRun | null>(null);

  const stop = async () => {
    if (!target) return;
    const id = target.task_id ?? target.id;
    try {
      await apiFetch(`/paper/stop/${id}`, { method: "POST" });
      toast.success(`Stop signal sent to ${target.run_name ?? id}`);
      runs.refetch();
    } catch (err) {
      toast.error(`Stop failed: ${(err as Error).message}`);
    }
  };

  return (
    <PageContainer
      title="Paper Runs"
      subtitle="Paper-broker sessions. Stop with friction; sandbox / paper banner is mandatory."
      extra={
        <Button variant="ghost" size="sm" onClick={() => runs.refetch()}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<PaperRun>
            rows={runs.data ?? []}
            rowKey={(r) => r.id}
            emptyState={
              runs.isPending ? (
                <span>Loading paper runs…</span>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Play className="h-6 w-6" />
                  <span>No paper runs yet.</span>
                </div>
              )
            }
            columns={[
              {
                key: "name",
                header: "Run",
                render: (r) => (
                  <div className="flex flex-col">
                    <span className="font-medium">{r.run_name ?? r.id}</span>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">
                      {r.task_id ?? r.id}
                    </span>
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
                      r.status === "running"
                        ? "positive"
                        : r.status === "stopped"
                          ? "warn"
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
                key: "cash",
                header: "Cash",
                width: 110,
                align: "right",
                render: (r) => <Numeric value={r.cash ?? null} kind="money" digits={0} color="neutral" />,
              },
              {
                key: "equity",
                header: "Equity",
                width: 110,
                align: "right",
                render: (r) => <Numeric value={r.equity ?? null} kind="money" digits={0} color="neutral" />,
              },
              {
                key: "pnl_session",
                header: "Session PnL",
                width: 130,
                align: "right",
                render: (r) => (
                  <Numeric value={r.pnl_session ?? null} kind="money" digits={0} color="auto" signed />
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
              {
                key: "actions",
                header: "Actions",
                width: 110,
                render: (r) => (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={r.status !== "running"}
                    onClick={(e) => {
                      e.stopPropagation();
                      setTarget(r);
                    }}
                    className="gap-1"
                  >
                    <Pause className="h-3.5 w-3.5" /> Stop
                  </Button>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>
      {target ? (
        <ConfirmFrictionDialog
          open={target != null}
          onOpenChange={(open) => {
            if (!open) setTarget(null);
          }}
          title={`Stop ${target.run_name ?? target.id}`}
          consequence="Sends a stop signal to the paper session. Open positions remain on the books — no flatten — until manually exited from the bot detail view."
          details={[
            { label: "Run name", value: target.run_name ?? "—" },
            { label: "Task id", value: target.task_id ?? target.id },
            { label: "Equity", value: target.equity != null ? `$${target.equity.toFixed(0)}` : "—" },
            {
              label: "Session PnL",
              value:
                target.pnl_session != null ? `$${target.pnl_session.toFixed(0)}` : "—",
              tone:
                target.pnl_session != null
                  ? target.pnl_session >= 0
                    ? "positive"
                    : "negative"
                  : "neutral",
            },
          ]}
          confirmPhrase="STOP"
          confirmLabel="Stop run"
          confirmVariant="destructive"
          onConfirm={stop}
        />
      ) : null}
    </PageContainer>
  );
}
