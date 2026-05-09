import { RefreshCcw, Wallet } from "lucide-react";

import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";

interface Position {
  vt_symbol: string;
  qty: number;
  avg_price: number;
  market_value: number | null;
  unrealized_pnl: number | null;
  realized_pnl?: number | null;
}

interface PortfolioSummary {
  total_equity?: number;
  cash?: number;
  unrealized_pnl?: number;
  realized_pnl?: number;
  net_exposure?: number;
  gross_exposure?: number;
}

export function PortfolioRoute() {
  const summary = useApiQuery<PortfolioSummary>({
    queryKey: ["portfolio", "summary"],
    path: "/portfolio/summary",
    refetchInterval: 5_000,
  });
  const positions = useApiQuery<Position[]>({
    queryKey: ["portfolio", "positions"],
    path: "/portfolio/positions",
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const sum = summary.data;

  return (
    <PageContainer
      title="Portfolio"
      subtitle="Equity, exposure, realized + unrealized PnL across the active workspace."
      extra={
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            summary.refetch();
            positions.refetch();
          }}
        >
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SummaryCard title="Total equity" value={sum?.total_equity ?? null} signed={false} />
        <SummaryCard title="Cash" value={sum?.cash ?? null} signed={false} />
        <SummaryCard title="Unrealized PnL" value={sum?.unrealized_pnl ?? null} signed />
        <SummaryCard title="Realized PnL" value={sum?.realized_pnl ?? null} signed />
        <SummaryCard
          title="Net exposure"
          value={sum?.net_exposure ?? null}
          signed
          digits={0}
        />
        <SummaryCard
          title="Gross exposure"
          value={sum?.gross_exposure ?? null}
          signed={false}
          digits={0}
        />
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Open positions</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="h-[calc(100vh-360px)]">
            <DataTable<Position>
              rows={positions.data ?? []}
              rowKey={(p) => p.vt_symbol}
              emptyState={
                <div className="flex flex-col items-center gap-2">
                  <Wallet className="h-6 w-6" />
                  <span>No open positions.</span>
                </div>
              }
              columns={[
                {
                  key: "vt_symbol",
                  header: "Symbol",
                  width: 160,
                  render: (p) => <span className="font-mono">{p.vt_symbol}</span>,
                },
                {
                  key: "qty",
                  header: "Qty",
                  width: 110,
                  align: "right",
                  render: (p) => (
                    <Numeric value={p.qty} kind="integer" digits={0} color="auto" signed />
                  ),
                },
                {
                  key: "avg_price",
                  header: "Avg price",
                  width: 110,
                  align: "right",
                  render: (p) => <Numeric value={p.avg_price} kind="decimal" digits={2} color="neutral" />,
                },
                {
                  key: "market_value",
                  header: "Market value",
                  width: 130,
                  align: "right",
                  render: (p) => (
                    <Numeric value={p.market_value} kind="money" digits={0} color="neutral" />
                  ),
                },
                {
                  key: "unrealized_pnl",
                  header: "Unrealized",
                  width: 130,
                  align: "right",
                  render: (p) => (
                    <Numeric value={p.unrealized_pnl} kind="money" digits={0} color="auto" signed />
                  ),
                },
                {
                  key: "realized_pnl",
                  header: "Realized",
                  width: 130,
                  align: "right",
                  render: (p) => (
                    <Numeric
                      value={p.realized_pnl ?? null}
                      kind="money"
                      digits={0}
                      color="auto"
                      signed
                    />
                  ),
                },
              ]}
            />
          </div>
        </CardContent>
      </Card>
    </PageContainer>
  );
}

interface SummaryCardProps {
  title: string;
  value: number | null;
  signed?: boolean;
  digits?: number;
}

function SummaryCard({ title, value, signed = false, digits = 0 }: SummaryCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Numeric
          value={value}
          kind="money"
          digits={digits}
          color={signed ? "auto" : "neutral"}
          signed={signed}
          className="text-2xl font-semibold"
        />
      </CardContent>
    </Card>
  );
}
