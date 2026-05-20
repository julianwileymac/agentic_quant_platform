import {
  ColorType,
  CrosshairMode,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
  createChart,
} from "lightweight-charts";
import { type MutableRefObject, useEffect, useMemo, useRef } from "react";

import { useMarketStore } from "@/store/market";
import type { LiveBar, LiveEvent, LiveQuote, LiveTick } from "@/lib/ws/types";

export interface OhlcSeed {
  time: number | string; // unix seconds OR ISO timestamp
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface OhlcChartProps {
  /** Symbol the chart locks onto. Live ticks for other symbols are ignored. */
  symbol: string;
  /** Optional historical seed loaded via REST before the WS connects. */
  seed?: OhlcSeed[];
  /** Render height in pixels. Width fills the parent. */
  height?: number;
}

const POS = "#10B981";
const NEG = "#EF4444";
const BG = "#0F172A";
const GRID = "rgba(148, 163, 184, 0.08)";
const TEXT = "#94A3B8";

/**
 * Canvas-backed candlestick + volume chart powered by `lightweight-charts`.
 *
 * Crucially, this component subscribes directly to the market store
 * via `getState()` and pushes incoming events into the series with
 * `series.update()` -- which redraws the canvas without triggering a
 * React reconciliation cycle. The component's own React tree only
 * renders once per mount; the canvas is the high-frequency surface.
 *
 * The blueprint mandate: "draw complex candlestick patterns with
 * exceptional performance, uniquely capable of handling tens of
 * thousands of data points". This implementation keeps a single
 * candlestick + histogram series, hands them seed data on mount, and
 * then aggregates live ticks into the most-recent bar.
 */
export function OhlcChart({ symbol, seed = [], height = 360 }: OhlcChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const lastBarRef = useRef<CandlestickData<UTCTimestamp> | null>(null);

  const seededSeries = useMemo<CandlestickData<UTCTimestamp>[]>(() => {
    return seed
      .map<CandlestickData<UTCTimestamp>>((b) => ({
        time: toUtc(b.time),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      }))
      .sort((a, b) => Number(a.time) - Number(b.time));
  }, [seed]);

  const seededVolume = useMemo<HistogramData<UTCTimestamp>[]>(() => {
    return seed
      .map<HistogramData<UTCTimestamp>>((b) => ({
        time: toUtc(b.time),
        value: b.volume ?? 0,
        color: b.close >= b.open ? `${POS}55` : `${NEG}55`,
      }))
      .sort((a, b) => Number(a.time) - Number(b.time));
  }, [seed]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: BG }, textColor: TEXT },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      width: container.clientWidth,
      height,
      autoSize: true,
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { borderColor: "rgba(148, 163, 184, 0.2)", scaleMargins: { top: 0.05, bottom: 0.2 } },
      timeScale: { borderColor: "rgba(148, 163, 184, 0.2)", secondsVisible: true, timeVisible: true },
    });
    chartRef.current = chart;

    const candles = chart.addCandlestickSeries({
      upColor: POS,
      downColor: NEG,
      wickUpColor: POS,
      wickDownColor: NEG,
      borderVisible: false,
    });
    candlesRef.current = candles;

    const volume = chart.addHistogramSeries({
      priceScaleId: "vol",
      priceFormat: { type: "volume" },
      color: `${POS}55`,
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
      borderColor: "rgba(148, 163, 184, 0.2)",
    });
    volumeRef.current = volume;

    if (seededSeries.length > 0) candles.setData(seededSeries);
    if (seededVolume.length > 0) volume.setData(seededVolume);
    chart.timeScale().fitContent();
    lastBarRef.current = seededSeries[seededSeries.length - 1] ?? null;

    /*
     * Subscribe to the market store imperatively so price ticks never
     * cause a React reconciliation. We use `useMarketStore.subscribe`
     * with a selector for the symbol-specific event so the listener
     * only fires when *this* chart's symbol updates.
     */
    const unsubscribe = useMarketStore.subscribe(
      (state) => state.latestBySymbol[symbol],
      (event) => {
        if (!event || !candlesRef.current || !volumeRef.current) return;
        applyEventToSeries(event, candlesRef.current, volumeRef.current, lastBarRef);
      },
      { fireImmediately: true },
    );

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      unsubscribe();
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
      volumeRef.current = null;
      lastBarRef.current = null;
    };
  }, [symbol, height, seededSeries, seededVolume]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}

function toUtc(value: number | string): UTCTimestamp {
  if (typeof value === "number") {
    if (value > 1e12) return Math.floor(value / 1000) as UTCTimestamp;
    return Math.floor(value) as UTCTimestamp;
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return 0 as UTCTimestamp;
  return Math.floor(d.getTime() / 1000) as UTCTimestamp;
}

function applyEventToSeries(
  event: LiveEvent,
  candles: ISeriesApi<"Candlestick">,
  volume: ISeriesApi<"Histogram">,
  lastBarRef: MutableRefObject<CandlestickData<UTCTimestamp> | null>,
) {
  const time = toUtc(event.timestamp);
  if (event.kind === "bar") {
    const bar = event as LiveBar;
    const next: CandlestickData<UTCTimestamp> = {
      time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    };
    candles.update(next);
    volume.update({
      time: time as Time,
      value: bar.volume,
      color: bar.close >= bar.open ? `${POS}55` : `${NEG}55`,
    });
    lastBarRef.current = next;
    return;
  }

  if (event.kind === "tick") {
    const tick = event as LiveTick;
    const last = lastBarRef.current;
    const price = tick.last;
    if (!last || time !== last.time) {
      const next: CandlestickData<UTCTimestamp> = {
        time,
        open: price,
        high: price,
        low: price,
        close: price,
      };
      candles.update(next);
      volume.update({ time: time as Time, value: tick.volume ?? 0, color: `${POS}55` });
      lastBarRef.current = next;
      return;
    }
    const next: CandlestickData<UTCTimestamp> = {
      time: last.time,
      open: last.open,
      high: Math.max(last.high, price),
      low: Math.min(last.low, price),
      close: price,
    };
    candles.update(next);
    volume.update({
      time: last.time as Time,
      value: tick.volume ?? 0,
      color: next.close >= next.open ? `${POS}55` : `${NEG}55`,
    });
    lastBarRef.current = next;
    return;
  }

  if (event.kind === "quote") {
    const quote = event as LiveQuote;
    const mid = (quote.bid_close + quote.ask_close) / 2;
    const last = lastBarRef.current;
    if (!last) {
      const next: CandlestickData<UTCTimestamp> = {
        time,
        open: mid,
        high: mid,
        low: mid,
        close: mid,
      };
      candles.update(next);
      lastBarRef.current = next;
    } else {
      const next: CandlestickData<UTCTimestamp> = {
        time: last.time,
        open: last.open,
        high: Math.max(last.high, mid),
        low: Math.min(last.low, mid),
        close: mid,
      };
      candles.update(next);
      lastBarRef.current = next;
    }
    return;
  }

  // Signals don't update the series; they're consumed by the order tape.
}
