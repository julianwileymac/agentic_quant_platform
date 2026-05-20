import { Bot, Plus, RefreshCcw } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

interface BotSummary {
  id: string;
  name: string;
  kind: "trading" | "research" | string;
  status?: string;
  strategy?: string;
  last_run_at?: string;
  pnl_total?: number;
  sharpe?: number;
  workspace?: string;
  project?: string;
}

export function BotsRoute() {
  const navigate = useNavigate();
  const bots = useApiQuery<BotSummary[]>({
    queryKey: ["bots"],
    path: "/bots",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  return (
    <PageContainer
      title="Bots"
      subtitle="Trading and research bots — the smallest deployable unit. Each row links to its lifecycle dashboard."
      extra={
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => bots.refetch()}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button asChild>
            <Link to="/bots/new">
              <Plus className="h-4 w-4" /> New Bot
            </Link>
          </Button>
        </div>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<BotSummary>
            rows={bots.data ?? []}
            rowKey={(b) => b.id}
            onRowClick={(b) => navigate(`/bots/${b.id}`)}
            emptyState={
              bots.isPending ? (
                <span>Loading bots…</span>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Bot className="h-6 w-6" />
                  <span>No bots yet. Create one to get started.</span>
                </div>
              )
            }
            columns={[
              {
                key: "name",
                header: "Bot",
                render: (b) => (
                  <div className="flex flex-col">
                    <span className="font-medium">{b.name}</span>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">{b.id}</span>
                  </div>
                ),
              },
              {
                key: "kind",
                header: "Kind",
                width: 110,
                render: (b) => (
                  <Badge variant={b.kind === "trading" ? "default" : "secondary"}>
                    {b.kind ?? "—"}
                  </Badge>
                ),
              },
              {
                key: "strategy",
                header: "Strategy / model",
                render: (b) => <span className="font-mono text-xs">{b.strategy ?? "—"}</span>,
              },
              {
                key: "status",
                header: "Status",
                width: 110,
                render: (b) => (
                  <Badge
                    variant={
                      b.status === "running"
                        ? "positive"
                        : b.status === "halted"
                          ? "negative"
                          : b.status === "deployed"
                            ? "warn"
                            : "secondary"
                    }
                  >
                    {b.status ?? "idle"}
                  </Badge>
                ),
              },
              {
                key: "pnl_total",
                header: "Total PnL",
                width: 130,
                align: "right",
                render: (b) => <Numeric value={b.pnl_total ?? null} kind="money" digits={0} color="auto" signed />,
              },
              {
                key: "sharpe",
                header: "Sharpe",
                width: 90,
                align: "right",
                render: (b) => <Numeric value={b.sharpe ?? null} kind="decimal" digits={2} color="auto" />,
              },
              {
                key: "last_run_at",
                header: "Last run",
                width: 130,
                align: "right",
                render: (b) => (
                  <span className="text-[var(--text-secondary)]">{b.last_run_at ? formatTime(b.last_run_at) : "—"}</span>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
