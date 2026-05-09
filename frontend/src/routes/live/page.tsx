import { Pause, Play, RefreshCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { OhlcChart, type OhlcSeed } from "@/components/charts/OhlcChart";
import { OrderBook, type OrderBookLevel } from "@/components/live/OrderBook";
import { OrderTape } from "@/components/live/OrderTape";
import { OrderTicket } from "@/components/live/OrderTicket";
import { PositionTable, type PositionRow } from "@/components/live/PositionTable";
import { WorkingOrders, type WorkingOrderRow } from "@/components/live/WorkingOrders";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useLiveStream } from "@/lib/ws";
import { Numeric } from "@/components/common/Numeric";
import { useLatestEvent } from "@/store/market";

interface SubscribeResponse {
  channel_id: string;
  ws_url?: string | null;
}

const DEFAULT_SYMBOL = "AAPL.NASDAQ";

/**
 * Live Trading Desk — the blueprint's priority surface.
 *
 * Layout:
 *
 *   ┌────────────────────────────┐ ┌─────────────────┐
 *   │ Resizable: chart | book   │ │ Order ticket    │
 *   │                            │ │ Positions       │
 *   │                            │ │ Working orders  │
 *   └────────────────────────────┘ │ Tape            │
 *                                   └─────────────────┘
 *
 * The left column is a `react-resizable-panels` PanelGroup so the
 * operator can drag the divider between the WebGL chart and the
 * virtualized order book to taste. Both panes subscribe to the same
 * shared market store; selectors keep re-renders surgical.
 */
export function LiveDeskRoute() {
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);
  const [pendingSymbol, setPendingSymbol] = useState(DEFAULT_SYMBOL);
  const [streaming, setStreaming] = useState(true);
  const [channelId, setChannelId] = useState<string | null>(null);

  // Open / close the live channel server-side via REST so the
  // backend knows which symbols to fan out from the producer.
  useEffect(() => {
    if (!streaming) {
      setChannelId(null);
      return;
    }
    let cancelled = false;
    apiFetch<SubscribeResponse>("/live/subscribe", {
      method: "POST",
      body: JSON.stringify({ vt_symbols: [symbol] }),
    })
      .then((res) => {
        if (!cancelled) setChannelId(res.channel_id);
      })
      .catch((err) => {
        toast.error(`Live subscribe failed: ${(err as Error).message}`);
        setChannelId(null);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, streaming]);

  const { status, error } = useLiveStream({ channelId });
  const latest = useLatestEvent(symbol);
  const referencePrice = useMemo(() => {
    if (!latest) return null;
    if (latest.kind === "quote") return (latest.bid_close + latest.ask_close) / 2;
    if (latest.kind === "tick") return latest.last;
    if (latest.kind === "bar") return latest.close;
    return null;
  }, [latest]);

  const seedQuery = useApiQuery<OhlcSeed[]>({
    queryKey: ["live-seed", symbol],
    path: `/live/history`,
    query: { vt_symbol: symbol, limit: 240 },
    staleTime: 60_000,
  });

  const bookQuery = useApiQuery<{ bids: OrderBookLevel[]; asks: OrderBookLevel[] }>({
    queryKey: ["live-book", symbol],
    path: `/live/book`,
    query: { vt_symbol: symbol },
    refetchInterval: streaming ? 1_500 : false,
  });

  const positionsQuery = useApiQuery<PositionRow[]>({
    queryKey: ["positions"],
    path: `/portfolio/positions`,
    refetchInterval: streaming ? 5_000 : false,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const workingQuery = useApiQuery<WorkingOrderRow[]>({
    queryKey: ["working-orders"],
    path: `/orders/working`,
    refetchInterval: streaming ? 3_000 : false,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const headerExtra = (
    <div className="flex items-center gap-2">
      <Badge variant={status === "open" ? "positive" : status === "connecting" ? "warn" : "secondary"}>
        WS {status}
      </Badge>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setStreaming((s) => !s)}
        className="gap-2"
      >
        {streaming ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        {streaming ? "Pause" : "Resume"}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          void seedQuery.refetch();
          void bookQuery.refetch();
          void workingQuery.refetch();
          void positionsQuery.refetch();
        }}
      >
        <RefreshCcw className="h-4 w-4" /> Refresh
      </Button>
    </div>
  );

  return (
    <PageContainer
      title="Live Trading Desk"
      subtitle="Throttled WebSocket pipeline · WebGL OHLC · purposeful-friction order ticket"
      extra={headerExtra}
      bleed
    >
      <div className="flex h-full flex-col gap-3 px-6 pb-6">
        <Card>
          <CardContent className="flex flex-wrap items-end gap-4 py-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ld-symbol">vt_symbol</Label>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setSymbol(pendingSymbol.trim().toUpperCase());
                }}
                className="flex gap-2"
              >
                <Input
                  id="ld-symbol"
                  value={pendingSymbol}
                  onChange={(e) => setPendingSymbol(e.target.value)}
                  className="w-48 font-mono"
                />
                <Button type="submit" variant="secondary" size="sm">
                  Set
                </Button>
              </form>
            </div>
            <div className="flex flex-col text-xs">
              <span className="text-[var(--text-secondary)]">Reference</span>
              <Numeric value={referencePrice} kind="decimal" digits={2} color="auto" className="text-base" />
            </div>
            {error ? (
              <Badge variant="negative" className="ml-auto">
                Stream error: {error}
              </Badge>
            ) : null}
          </CardContent>
        </Card>

        <PanelGroup direction="horizontal" className="flex flex-1 gap-2">
          <Panel defaultSize={70} minSize={45}>
            <PanelGroup direction="horizontal" className="flex h-full gap-2">
              <Panel defaultSize={70} minSize={40}>
                <Card className="flex h-full flex-col">
                  <CardHeader>
                    <CardTitle>OHLC · {symbol}</CardTitle>
                    <Badge variant="secondary">WebGL</Badge>
                  </CardHeader>
                  <CardContent className="flex-1 p-0">
                    <OhlcChart
                      symbol={symbol}
                      seed={seedQuery.data ?? []}
                      height={420}
                    />
                  </CardContent>
                </Card>
              </Panel>
              <PanelResizeHandle className="w-1 cursor-col-resize bg-[var(--border-default)]" />
              <Panel defaultSize={30} minSize={20}>
                <Card className="flex h-full flex-col">
                  <CardHeader>
                    <CardTitle>Order book</CardTitle>
                  </CardHeader>
                  <CardContent className="flex-1 p-0">
                    <OrderBook
                      symbol={symbol}
                      bids={bookQuery.data?.bids ?? []}
                      asks={bookQuery.data?.asks ?? []}
                    />
                  </CardContent>
                </Card>
              </Panel>
            </PanelGroup>
          </Panel>
          <PanelResizeHandle className="w-1 cursor-col-resize bg-[var(--border-default)]" />
          <Panel defaultSize={30} minSize={22}>
            <Tabs defaultValue="ticket" className="flex h-full flex-col gap-2">
              <TabsList className="self-start">
                <TabsTrigger value="ticket">Ticket</TabsTrigger>
                <TabsTrigger value="positions">Positions</TabsTrigger>
                <TabsTrigger value="orders">Orders</TabsTrigger>
                <TabsTrigger value="tape">Tape</TabsTrigger>
              </TabsList>
              <TabsContent value="ticket" className="flex-1">
                <OrderTicket symbol={symbol} />
              </TabsContent>
              <TabsContent value="positions" className="flex-1">
                <PositionTable positions={positionsQuery.data ?? []} />
              </TabsContent>
              <TabsContent value="orders" className="flex-1">
                <WorkingOrders
                  orders={workingQuery.data ?? []}
                  onRefresh={() => void workingQuery.refetch()}
                />
              </TabsContent>
              <TabsContent value="tape" className="flex-1">
                <OrderTape symbol={symbol} />
              </TabsContent>
            </Tabs>
          </Panel>
        </PanelGroup>
      </div>
    </PageContainer>
  );
}
