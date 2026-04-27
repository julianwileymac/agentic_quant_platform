"use client";

import { Alert, Empty, Select, Space, Spin, Tag, Typography } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";

import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface Bar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface SignalRow {
  timestamp?: string;
  ts?: string;
  vt_symbol?: string;
  side?: string;
  action?: string;
  signal?: number;
  size?: number;
  size_pct?: number;
  rationale?: string;
}

interface TradeRow {
  timestamp?: string;
  entry_time?: string;
  vt_symbol?: string;
  side?: string;
  qty?: number;
  price?: number;
  pnl?: number;
}

interface TimelineResp {
  backtest_id: string;
  vt_symbol: string | null;
  available_symbols: string[];
  bars: Bar[];
  trades: TradeRow[];
  signals: SignalRow[];
  orders: SignalRow[];
}

function asTime(value: string | undefined): number | undefined {
  if (!value) return undefined;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return undefined;
  return Math.floor(t / 1000);
}

function classify(side: string | undefined): "buy" | "sell" | undefined {
  if (!side) return undefined;
  const v = side.toString().toUpperCase();
  if (["BUY", "LONG", "OPEN_LONG"].includes(v)) return "buy";
  if (["SELL", "SHORT", "CLOSE", "CLOSE_LONG", "EXIT"].includes(v)) return "sell";
  return undefined;
}

export function BacktestTimelineChart({ backtestId }: { backtestId: string }) {
  const [vtSymbol, setVtSymbol] = useState<string | undefined>(undefined);

  const timeline = useApiQuery<TimelineResp>({
    queryKey: ["backtest", "timeline", backtestId, vtSymbol ?? "auto"],
    path: `/backtest/runs/${backtestId}/timeline`,
    query: vtSymbol ? { vt_symbol: vtSymbol } : undefined,
  });

  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<unknown>(null);

  useEffect(() => {
    if (!timeline.data || !containerRef.current) return;
    const bars = timeline.data.bars;
    if (bars.length === 0) return;

    let cancelled = false;
    let cleanup: (() => void) | undefined;

    (async () => {
      const lwc = await import("lightweight-charts");
      if (cancelled || !containerRef.current) return;
      const container = containerRef.current;
      container.innerHTML = "";
      const chart = lwc.createChart(container, {
        width: container.clientWidth,
        height: 420,
        layout: {
          background: { color: "transparent" },
          textColor: "rgba(255,255,255,0.85)",
        },
        grid: {
          horzLines: { color: "rgba(127,127,127,0.15)" },
          vertLines: { color: "rgba(127,127,127,0.10)" },
        },
        timeScale: { timeVisible: true, secondsVisible: false },
      });
      chartRef.current = chart;

      const series = chart.addCandlestickSeries({
        upColor: "#10b981",
        downColor: "#ef4444",
        borderVisible: false,
        wickUpColor: "#10b981",
        wickDownColor: "#ef4444",
      });
      series.setData(
        bars
          .map((b) => {
            const t = asTime(b.timestamp);
            return t
              ? {
                  time: t as never,
                  open: Number(b.open),
                  high: Number(b.high),
                  low: Number(b.low),
                  close: Number(b.close),
                }
              : null;
          })
          .filter(Boolean) as never,
      );

      const markers: Array<{
        time: number;
        position: "aboveBar" | "belowBar";
        color: string;
        shape: "arrowUp" | "arrowDown" | "circle";
        text?: string;
      }> = [];

      const seenMarkers = new Set<string>();
      const pushMarker = (
        rawTs: string | undefined,
        side: string | undefined,
        text?: string,
        kindOverride?: "buy" | "sell",
      ) => {
        const t = asTime(rawTs);
        if (!t) return;
        const kind = kindOverride ?? classify(side);
        if (!kind) return;
        const key = `${t}-${kind}-${text ?? ""}`;
        if (seenMarkers.has(key)) return;
        seenMarkers.add(key);
        markers.push({
          time: t,
          position: kind === "buy" ? "belowBar" : "aboveBar",
          color: kind === "buy" ? "#10b981" : "#ef4444",
          shape: kind === "buy" ? "arrowUp" : "arrowDown",
          text,
        });
      };

      for (const sig of timeline.data.signals) {
        const sideLike = sig.side ?? sig.action;
        let kind: "buy" | "sell" | undefined;
        if (typeof sig.signal === "number") {
          if (sig.signal > 0) kind = "buy";
          else if (sig.signal < 0) kind = "sell";
        }
        pushMarker(sig.timestamp ?? sig.ts, sideLike, sig.rationale ?? "signal", kind);
      }
      for (const tr of timeline.data.trades) {
        pushMarker(tr.timestamp ?? tr.entry_time, tr.side, "trade");
      }
      markers.sort((a, b) => a.time - b.time);
      if (markers.length > 0) {
        series.setMarkers(markers as never);
      }

      chart.timeScale().fitContent();
      const onResize = () => {
        if (containerRef.current) {
          chart.resize(containerRef.current.clientWidth, 420);
        }
      };
      window.addEventListener("resize", onResize);
      cleanup = () => {
        window.removeEventListener("resize", onResize);
        chart.remove();
      };
    })().catch(() => {
      /* noop */
    });

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [timeline.data]);

  const symbols = useMemo(() => {
    const out = new Set<string>(timeline.data?.available_symbols ?? []);
    if (timeline.data?.vt_symbol) out.add(timeline.data.vt_symbol);
    return Array.from(out).sort();
  }, [timeline.data]);

  if (timeline.isLoading) return <Spin />;
  if (timeline.error) return <Alert type="error" message={timeline.error.message} />;

  const data = timeline.data;
  const hasBars = (data?.bars?.length ?? 0) > 0;

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Space>
        <Text type="secondary">Symbol:</Text>
        <Select
          value={vtSymbol ?? data?.vt_symbol ?? undefined}
          onChange={(v) => setVtSymbol(v)}
          options={symbols.map((s) => ({ value: s, label: s }))}
          placeholder="Pick a symbol"
          style={{ minWidth: 180 }}
        />
        <Tag color="green">trades: {data?.trades.length ?? 0}</Tag>
        <Tag color="purple">signals: {data?.signals.length ?? 0}</Tag>
        <Tag color="blue">orders: {data?.orders.length ?? 0}</Tag>
      </Space>
      {!hasBars ? (
        <Empty
          description={
            data?.vt_symbol
              ? "No OHLCV data found in DuckDB for this run window. Run `make ingest`."
              : "This run did not record per-symbol decisions."
          }
        />
      ) : (
        <div ref={containerRef} style={{ width: "100%", height: 420 }} />
      )}
    </Space>
  );
}
