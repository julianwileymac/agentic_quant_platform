import { Numeric } from "@/components/common/Numeric";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface PositionRow {
  vt_symbol: string;
  qty: number;
  avg_price: number;
  market_value: number | null;
  unrealized_pnl: number | null;
}

interface PositionTableProps {
  positions: PositionRow[];
}

export function PositionTable({ positions }: PositionTableProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Open positions</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid grid-cols-5 gap-2 border-b border-[var(--border-default)] px-4 py-2 text-[10px] uppercase tracking-wider text-[var(--text-secondary)]">
          <span>Symbol</span>
          <span className="text-right">Qty</span>
          <span className="text-right">Avg</span>
          <span className="text-right">Mkt value</span>
          <span className="text-right">Unrealized</span>
        </div>
        <ul>
          {positions.length === 0 ? (
            <li className="px-4 py-3 text-center text-xs text-[var(--text-secondary)]">
              No open positions.
            </li>
          ) : (
            positions.map((p) => (
              <li
                key={p.vt_symbol}
                className="grid grid-cols-5 items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-1.5 tabular last:border-b-0"
              >
                <span className="font-mono text-xs">{p.vt_symbol}</span>
                <span className="text-right">
                  <Numeric value={p.qty} kind="integer" digits={0} color="auto" signed />
                </span>
                <span className="text-right">
                  <Numeric value={p.avg_price} kind="decimal" digits={2} color="neutral" />
                </span>
                <span className="text-right">
                  <Numeric value={p.market_value} kind="money" digits={0} color="neutral" />
                </span>
                <span className="text-right">
                  <Numeric value={p.unrealized_pnl} kind="money" digits={0} color="auto" signed />
                </span>
              </li>
            ))
          )}
        </ul>
      </CardContent>
    </Card>
  );
}
