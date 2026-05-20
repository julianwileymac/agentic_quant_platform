import {
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
  createChart,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";

import { useChatStream } from "@/lib/ws/useChatStream";

interface LobReplayChartProps {
  /** Celery task ID. ``null`` keeps the chart blank. */
  taskId: string | null;
}

/**
 * Live equity + position curve for an HFT LOB backtest.
 *
 * Subscribes to the existing ``/chat/stream/{task_id}`` WebSocket via
 * ``useChatStream`` (the throttled, rAF-batched hook from the AQP
 * frontend WS layer). Each progress event carries ``equity`` +
 * ``position`` extras (see :mod:`aqp.tasks.hft_tasks`); we map them
 * onto two ``lightweight-charts`` line series.
 *
 * The component never re-renders the React tree on incoming frames —
 * it pushes data through ``series.update()`` directly so the canvas
 * draws at native FPS regardless of stream rate.
 */
export function LobReplayChart({ taskId }: LobReplayChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const equityRef = useRef<ISeriesApi<"Line"> | null>(null);
  const positionRef = useRef<ISeriesApi<"Line"> | null>(null);

  const { events } = useChatStream(taskId);

  // Convert the raw progress events into chart points. ``useChatStream``
  // already throttles via the WS pipeline so we render whatever we get.
  // Under ``exactOptionalPropertyTypes`` we cannot store ``undefined`` on
  // optional keys; we use ``null`` instead and filter at series-update time.
  const points = useMemo(() => {
    const out: { time: UTCTimestamp; equity: number | null; position: number | null }[] = [];
    for (const e of events) {
      const ts = typeof e.timestamp === "number" ? e.timestamp : Date.parse(String(e.timestamp));
      if (!Number.isFinite(ts) || ts <= 0) continue;
      const time = (Math.floor(ts > 1e12 ? ts / 1000 : ts) as unknown) as UTCTimestamp;
      const equity = typeof e.equity === "number" ? e.equity : null;
      const position = typeof e.position === "number" ? e.position : null;
      if (equity === null && position === null) continue;
      out.push({ time, equity, position });
    }
    return out;
  }, [events]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: "#0F172A" },
        textColor: "#94A3B8",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.08)" },
        horzLines: { color: "rgba(148, 163, 184, 0.08)" },
      },
      width: container.clientWidth,
      height: container.clientHeight || 400,
      autoSize: true,
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { borderColor: "rgba(148, 163, 184, 0.2)" },
      leftPriceScale: { borderColor: "rgba(148, 163, 184, 0.2)", visible: true },
      timeScale: { borderColor: "rgba(148, 163, 184, 0.2)", secondsVisible: true, timeVisible: true },
    });
    chartRef.current = chart;

    const equitySeries = chart.addLineSeries({
      color: "#10B981",
      lineWidth: 2,
      priceScaleId: "right",
      title: "equity",
    });
    const positionSeries = chart.addLineSeries({
      color: "#F59E0B",
      lineWidth: 2,
      priceScaleId: "left",
      title: "position",
    });
    equityRef.current = equitySeries;
    positionRef.current = positionSeries;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 400,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      equityRef.current = null;
      positionRef.current = null;
    };
  }, []);

  // Push every observed point into the line series. ``setData`` is
  // expensive but the throttled stream rate keeps it tractable; for
  // very long replays we'd switch to incremental ``update`` calls.
  useEffect(() => {
    const eq = equityRef.current;
    const pos = positionRef.current;
    if (!eq || !pos) return;
    const equityData: LineData<UTCTimestamp>[] = points
      .filter((p): p is typeof p & { equity: number } => typeof p.equity === "number")
      .map((p) => ({ time: p.time, value: p.equity }));
    const positionData: LineData<UTCTimestamp>[] = points
      .filter((p): p is typeof p & { position: number } => typeof p.position === "number")
      .map((p) => ({ time: p.time, value: p.position }));
    if (equityData.length > 0) eq.setData(equityData);
    if (positionData.length > 0) pos.setData(positionData);
    if ((equityData.length || positionData.length) && chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [points]);

  return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
}
