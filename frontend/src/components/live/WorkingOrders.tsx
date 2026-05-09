import { X } from "lucide-react";

import { Numeric } from "@/components/common/Numeric";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";

export interface WorkingOrderRow {
  id: string;
  vt_symbol: string;
  side: "buy" | "sell";
  qty: number;
  filled_qty?: number;
  limit_price?: number;
  status: string;
  created_at: string;
}

interface WorkingOrdersProps {
  orders: WorkingOrderRow[];
  onRefresh: () => void;
}

export function WorkingOrders({ orders, onRefresh }: WorkingOrdersProps) {
  const cancel = async (id: string) => {
    try {
      await apiFetch(`/orders/${id}`, { method: "DELETE" });
      toast.success(`Order ${id} cancelled`);
      onRefresh();
    } catch (err) {
      toast.error(`Cancel failed: ${(err as Error).message}`);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>Working orders</CardTitle>
        <Badge variant="secondary">{orders.length}</Badge>
      </CardHeader>
      <CardContent className="p-0">
        <ul>
          {orders.length === 0 ? (
            <li className="px-4 py-3 text-center text-xs text-[var(--text-secondary)]">
              No working orders.
            </li>
          ) : (
            orders.map((o) => (
              <li
                key={o.id}
                className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 border-b border-[var(--border-subtle)] px-4 py-2 last:border-b-0"
              >
                <div className="flex flex-col">
                  <span className="font-mono text-xs">{o.vt_symbol}</span>
                  <span className="text-[10px] text-[var(--text-secondary)]">{o.status}</span>
                </div>
                <Badge variant={o.side === "buy" ? "positive" : "negative"}>
                  {o.side.toUpperCase()}
                </Badge>
                <span className="text-right tabular text-xs">
                  <Numeric value={o.qty} kind="integer" digits={0} color="neutral" /> @ {" "}
                  <Numeric value={o.limit_price ?? null} kind="decimal" digits={2} color="neutral" />
                </span>
                <Button variant="ghost" size="icon" onClick={() => cancel(o.id)} aria-label={`Cancel order ${o.id}`}>
                  <X className="h-4 w-4 text-[var(--neg-fg)]" />
                </Button>
              </li>
            ))
          )}
        </ul>
      </CardContent>
    </Card>
  );
}
