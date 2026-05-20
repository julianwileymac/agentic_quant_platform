import * as d3 from "d3";
import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface EquityPoint {
  timestamp: string | number;
  value: number;
}

interface EquityChartProps {
  data: EquityPoint[];
  /** Optional benchmark series rendered as a dashed line. */
  benchmark?: EquityPoint[];
  /** Render height in pixels. Width fills the parent. */
  height?: number;
  /** Force the y-axis to start at zero (useful for drawdown). */
  zeroBased?: boolean;
  /** Whether to render a drawdown band at the bottom of the chart. */
  showDrawdown?: boolean;
  /** Format the y-axis ticks. Defaults to a locale-aware decimal. */
  formatY?: (n: number) => string;
  className?: string;
}

const POS = "#10B981";
const NEG = "#EF4444";
const PRIMARY = "#3B82F6";
const GRID = "rgba(148, 163, 184, 0.12)";
const TEXT = "#94A3B8";

/**
 * D3-driven equity curve. Renders an area + line above an optional
 * benchmark dashed line, with a drawdown band beneath. The blueprint
 * mandates D3 for ML / loss curves and we reuse the same primitive
 * for backtest equity, RL run equity, and ML training loss curves.
 *
 * The component is imperative — D3 owns the SVG nodes inside a
 * memoised effect so a tick update never crosses the React reconciler.
 */
export function EquityChart({
  data,
  benchmark,
  height = 320,
  zeroBased = false,
  showDrawdown = true,
  formatY,
  className,
}: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [width, setWidth] = useState(0);

  // Track container size so the chart redraws on layout changes.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setWidth(Math.max(120, entry.contentRect.width));
    });
    ro.observe(node);
    setWidth(node.clientWidth);
    return () => ro.disconnect();
  }, []);

  /** Compute drawdown series: (current_value - peak) / peak. */
  const drawdown = useMemo(() => {
    if (!showDrawdown) return [];
    let peak = -Infinity;
    return data.map((d) => {
      const v = d.value;
      peak = Math.max(peak, v);
      return {
        timestamp: d.timestamp,
        value: peak === 0 ? 0 : (v - peak) / Math.abs(peak),
      };
    });
  }, [data, showDrawdown]);

  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl || width <= 0 || data.length === 0) return;
    const svg = d3.select(svgEl);
    svg.selectAll("*").remove();

    const margin = { top: 12, right: 16, bottom: 22, left: 50 };
    const ddHeight = showDrawdown ? Math.min(60, Math.floor(height * 0.25)) : 0;
    const mainHeight = Math.max(80, height - margin.top - margin.bottom - ddHeight);
    const innerWidth = Math.max(40, width - margin.left - margin.right);

    /** X parser handles both ISO strings and numeric timestamps. */
    const parseTs = (raw: string | number): Date => {
      if (typeof raw === "number") return new Date(raw > 1e12 ? raw : raw * 1000);
      const parsed = new Date(raw);
      return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
    };

    const points = data.map((d) => ({ x: parseTs(d.timestamp), y: d.value }));
    const benchmarkPoints = (benchmark ?? []).map((d) => ({ x: parseTs(d.timestamp), y: d.value }));

    const xExtent = d3.extent(points, (d) => d.x) as [Date, Date];
    const yMin = zeroBased ? 0 : (d3.min(points, (d) => d.y) ?? 0);
    const yMax = d3.max(points, (d) => d.y) ?? 1;
    const yPad = (yMax - yMin) * 0.05;

    const xScale = d3.scaleTime().domain(xExtent).range([0, innerWidth]);
    const yScale = d3
      .scaleLinear()
      .domain([yMin - yPad, yMax + yPad])
      .nice()
      .range([mainHeight, 0]);

    const root = svg
      .attr("viewBox", `0 0 ${width} ${height}`)
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    // Grid lines.
    root
      .append("g")
      .attr("class", "y-grid")
      .selectAll("line")
      .data(yScale.ticks(5))
      .enter()
      .append("line")
      .attr("x1", 0)
      .attr("x2", innerWidth)
      .attr("y1", (d) => yScale(d))
      .attr("y2", (d) => yScale(d))
      .attr("stroke", GRID);

    // Area under the line — semantic colour by overall direction.
    const direction =
      points.length >= 2 && points[points.length - 1]!.y >= points[0]!.y ? "pos" : "neg";
    const areaColor = direction === "pos" ? POS : NEG;
    const baseline = Math.max(yScale.domain()[0]!, 0);
    const area = d3
      .area<{ x: Date; y: number }>()
      .x((d) => xScale(d.x))
      .y0(yScale(baseline))
      .y1((d) => yScale(d.y))
      .curve(d3.curveMonotoneX);
    root
      .append("path")
      .datum(points)
      .attr("d", area)
      .attr("fill", areaColor)
      .attr("fill-opacity", 0.12);

    // Primary line.
    const line = d3
      .line<{ x: Date; y: number }>()
      .x((d) => xScale(d.x))
      .y((d) => yScale(d.y))
      .curve(d3.curveMonotoneX);
    root
      .append("path")
      .datum(points)
      .attr("d", line)
      .attr("fill", "none")
      .attr("stroke", PRIMARY)
      .attr("stroke-width", 1.6);

    // Optional benchmark dashed line.
    if (benchmarkPoints.length >= 2) {
      root
        .append("path")
        .datum(benchmarkPoints)
        .attr("d", line)
        .attr("fill", "none")
        .attr("stroke", TEXT)
        .attr("stroke-width", 1)
        .attr("stroke-dasharray", "4 4");
    }

    // X axis.
    const xAxis = d3
      .axisBottom(xScale)
      .ticks(Math.min(8, Math.floor(innerWidth / 90)))
      .tickFormat((d) => d3.timeFormat("%b %d")(d as Date));
    root
      .append("g")
      .attr("transform", `translate(0,${mainHeight})`)
      .call(xAxis)
      .call((g) => g.select(".domain").attr("stroke", GRID))
      .call((g) => g.selectAll(".tick text").attr("fill", TEXT).attr("font-size", 10));

    // Y axis.
    const fmt = formatY ?? ((n: number) => d3.format(".2~f")(n));
    const yAxis = d3.axisLeft(yScale).ticks(5).tickFormat((d) => fmt(d as number));
    root
      .append("g")
      .call(yAxis)
      .call((g) => g.select(".domain").attr("stroke", GRID))
      .call((g) =>
        g
          .selectAll(".tick text")
          .attr("fill", TEXT)
          .attr("font-size", 10)
          .style("font-variant-numeric", "tabular-nums"),
      );

    // Drawdown band.
    if (showDrawdown && drawdown.length >= 2) {
      const ddPoints = drawdown.map((d) => ({ x: parseTs(d.timestamp), y: d.value }));
      const ddYMin = d3.min(ddPoints, (d) => d.y) ?? -0.05;
      const ddScale = d3.scaleLinear().domain([ddYMin, 0]).range([ddHeight, 0]);
      const ddArea = d3
        .area<{ x: Date; y: number }>()
        .x((d) => xScale(d.x))
        .y0(ddScale(0))
        .y1((d) => ddScale(d.y))
        .curve(d3.curveMonotoneX);
      const ddRoot = root
        .append("g")
        .attr("transform", `translate(0,${mainHeight + 12})`);
      ddRoot
        .append("path")
        .datum(ddPoints)
        .attr("d", ddArea)
        .attr("fill", NEG)
        .attr("fill-opacity", 0.25);
      ddRoot
        .append("text")
        .attr("x", 0)
        .attr("y", -2)
        .attr("fill", TEXT)
        .attr("font-size", 9)
        .text("Drawdown");
    }
  }, [data, benchmark, drawdown, height, width, zeroBased, showDrawdown, formatY]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative w-full",
        data.length === 0 && "flex items-center justify-center text-sm text-[var(--text-secondary)]",
        className,
      )}
      style={{ height }}
      data-equity-chart="true"
    >
      {data.length === 0 ? (
        <span>No data available.</span>
      ) : (
        <svg ref={svgRef} width={width} height={height} role="img" />
      )}
    </div>
  );
}
