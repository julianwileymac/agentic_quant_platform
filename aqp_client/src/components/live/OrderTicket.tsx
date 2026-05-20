import { ArrowDownRight, ArrowUpRight, Send } from "lucide-react";
import { useMemo, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { Numeric } from "@/components/common/Numeric";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { apiFetch, ApiError } from "@/lib/api/client";
import { useLatestEvent } from "@/store/market";
import { useTenancyStore } from "@/store/tenancy";

interface OrderTicketProps {
  symbol: string;
  /** Default initial quantity. Operators can override. */
  defaultQty?: number;
}

type Side = "buy" | "sell";
type OrderType = "market" | "limit" | "stop";

interface SubmitPayload {
  vt_symbol: string;
  side: Side;
  qty: number;
  order_type: OrderType;
  limit_price?: number;
  stop_price?: number;
  paper: boolean;
}

/**
 * Manual order ticket. Submitting routes through {@link ConfirmFrictionDialog}
 * (typed-confirmation phrase + risk parameters) before any POST is
 * issued to the FastAPI `/orders` endpoint. The friction is mandatory
 * even in sandbox / paper mode so muscle memory is the same in live.
 *
 * Side buttons are colour-coded with semantic +/- tokens; a sandbox /
 * paper caption is added when the active mode is non-live, satisfying
 * the blueprint's "Simulated execution" requirement.
 */
export function OrderTicket({ symbol, defaultQty = 100 }: OrderTicketProps) {
  const mode = useTenancyStore((s) => s.mode);
  const latest = useLatestEvent(symbol);
  const reference = useMemo(() => {
    if (!latest) return null;
    if (latest.kind === "quote") return (latest.bid_close + latest.ask_close) / 2;
    if (latest.kind === "tick") return latest.last;
    if (latest.kind === "bar") return latest.close;
    return null;
  }, [latest]);

  const [side, setSide] = useState<Side>("buy");
  const [orderType, setOrderType] = useState<OrderType>("limit");
  const [qty, setQty] = useState(defaultQty);
  const [limit, setLimit] = useState<number | "">("");
  const [stop, setStop] = useState<number | "">("");
  const [confirmOpen, setConfirmOpen] = useState(false);

  const limitValue = orderType === "limit" ? Number(limit) : reference;
  const notional = limitValue && qty ? Math.abs(qty * limitValue) : null;

  const ready = qty > 0 && (orderType !== "limit" || (typeof limit === "number" && limit > 0));

  const submit = async () => {
    const payload: SubmitPayload = {
      vt_symbol: symbol,
      side,
      qty,
      order_type: orderType,
      paper: mode !== "live",
    };
    if (orderType === "limit" && typeof limit === "number") payload.limit_price = limit;
    if (orderType === "stop" && typeof stop === "number") payload.stop_price = stop;
    try {
      const res = await apiFetch<{ order_id?: string }>("/orders", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      toast.success(
        `${side === "buy" ? "Bought" : "Sold"} ${qty} ${symbol}${
          res.order_id ? ` (#${res.order_id})` : ""
        }`,
        {
          description:
            mode === "live"
              ? "Order routed to live broker"
              : "Simulated execution — paper broker",
        },
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Order rejected: ${message}`);
      throw err;
    }
  };

  return (
    <>
      <Card className="h-full">
        <CardHeader>
          <CardTitle>Order ticket</CardTitle>
          <Badge variant={mode === "live" ? "positive" : "warn"}>
            {mode === "live" ? "Live execution" : "Simulated execution"}
          </Badge>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant={side === "buy" ? "positive" : "outline"}
              onClick={() => setSide("buy")}
              className="gap-2"
            >
              <ArrowUpRight className="h-4 w-4" /> Buy
            </Button>
            <Button
              type="button"
              variant={side === "sell" ? "destructive" : "outline"}
              onClick={() => setSide("sell")}
              className="gap-2"
            >
              <ArrowDownRight className="h-4 w-4" /> Sell
            </Button>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ot-symbol">Symbol</Label>
            <Input id="ot-symbol" value={symbol} readOnly className="font-mono" />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ot-qty">Quantity</Label>
            <Input
              id="ot-qty"
              type="number"
              min={1}
              value={qty}
              onChange={(e) => setQty(Math.max(0, Number(e.target.value) || 0))}
              className="font-mono"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Order type</Label>
            <div className="grid grid-cols-3 gap-1">
              {(["market", "limit", "stop"] as const).map((t) => (
                <Button
                  key={t}
                  type="button"
                  variant={orderType === t ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => setOrderType(t)}
                  className="capitalize"
                >
                  {t}
                </Button>
              ))}
            </div>
          </div>

          {orderType === "limit" ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ot-limit">Limit price</Label>
              <Input
                id="ot-limit"
                type="number"
                min={0}
                step="0.01"
                value={limit}
                onChange={(e) => setLimit(e.target.value === "" ? "" : Number(e.target.value))}
                className="font-mono"
              />
            </div>
          ) : null}

          {orderType === "stop" ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ot-stop">Stop price</Label>
              <Input
                id="ot-stop"
                type="number"
                min={0}
                step="0.01"
                value={stop}
                onChange={(e) => setStop(e.target.value === "" ? "" : Number(e.target.value))}
                className="font-mono"
              />
            </div>
          ) : null}

          <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-[var(--text-secondary)]">Reference</span>
              <Numeric value={reference} kind="decimal" digits={2} color="auto" />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[var(--text-secondary)]">Notional</span>
              <Numeric value={notional} kind="money" digits={0} color="neutral" />
            </div>
          </div>

          <Button
            onClick={() => setConfirmOpen(true)}
            disabled={!ready}
            variant={side === "buy" ? "positive" : "destructive"}
            className="gap-2"
          >
            <Send className="h-4 w-4" />
            {side === "buy" ? "Submit buy" : "Submit sell"}
          </Button>
        </CardContent>
      </Card>

      <ConfirmFrictionDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Submit ${side.toUpperCase()} ${symbol}`}
        consequence={
          mode === "live"
            ? "This routes the order to the live broker immediately. Real capital is at risk and the action is irreversible once filled."
            : "This routes the order to the paper broker. No real capital is at risk; fills are simulated against the active sandbox tenant."
        }
        details={[
          { label: "Symbol", value: symbol },
          { label: "Side", value: side.toUpperCase(), tone: side === "buy" ? "positive" : "negative" },
          { label: "Quantity", value: qty },
          { label: "Order type", value: orderType },
          ...(orderType === "limit" && typeof limit === "number"
            ? [{ label: "Limit price", value: limit }]
            : []),
          ...(orderType === "stop" && typeof stop === "number"
            ? [{ label: "Stop price", value: stop }]
            : []),
          {
            label: "Reference price",
            value: reference != null ? reference.toFixed(2) : "—",
          },
          {
            label: "Notional",
            value: notional != null ? `$${notional.toFixed(0)}` : "—",
            tone: "warn",
          },
          { label: "Mode", value: mode.toUpperCase(), tone: mode === "live" ? "warn" : "neutral" },
        ]}
        confirmPhrase={mode === "live" ? "FIRE" : "SUBMIT"}
        confirmLabel={`Submit ${side}`}
        confirmVariant={side === "buy" ? "default" : "destructive"}
        onConfirm={submit}
      />
    </>
  );
}
