import * as d3 from "d3";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

interface PercentileFanProps {
  /** Paths matrix [paths][steps] in absolute price-space. */
  paths: number[][];
  className?: string;
}

const BANDS: Array<{ lo: number; hi: number; opacity: number }> = [
  { lo: 0.05, hi: 0.95, opacity: 0.18 },
  { lo: 0.1, hi: 0.9, opacity: 0.28 },
  { lo: 0.25, hi: 0.75, opacity: 0.45 },
];

/**
 * D3 percentile-fan chart for Monte Carlo path simulations. Renders 5/95,
 * 10/90, and 25/75 quantile bands plus the median; ports the legacy
 * webui's d3 implementation but uses the AQP token palette.
 */
export function PercentileFan({ paths, className }: PercentileFanProps) {
  const ref = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    if (paths.length === 0 || paths[0]?.length === 0) {
      d3.select(svg).selectAll("*").remove();
      return;
    }
    const rect = svg.getBoundingClientRect();
    const width = Math.max(rect.width || 600, 320);
    const height = Math.max(rect.height || 240, 180);
    const margin = { top: 14, right: 28, bottom: 28, left: 56 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const steps = paths[0]?.length ?? 0;
    const stepIndices = d3.range(steps);
    const quantilesAtStep = stepIndices.map((t) => {
      const col = paths.map((p) => p[t] ?? 0);
      col.sort(d3.ascending);
      const q = (p: number) => d3.quantileSorted(col, p) ?? 0;
      return {
        t,
        q05: q(0.05),
        q10: q(0.1),
        q25: q(0.25),
        q50: q(0.5),
        q75: q(0.75),
        q90: q(0.9),
        q95: q(0.95),
      };
    });

    const yMin = d3.min(quantilesAtStep, (d) => d.q05) ?? 0;
    const yMax = d3.max(quantilesAtStep, (d) => d.q95) ?? 1;

    const x = d3.scaleLinear().domain([0, steps - 1]).range([0, innerW]);
    const y = d3.scaleLinear().domain([yMin, yMax]).nice().range([innerH, 0]);

    d3.select(svg).selectAll("*").remove();
    const root = d3
      .select(svg)
      .attr("viewBox", `0 0 ${width} ${height}`)
      .append("g")
      .attr("transform", `translate(${margin.left}, ${margin.top})`);

    BANDS.forEach((b) => {
      const path = d3
        .area<(typeof quantilesAtStep)[number]>()
        .x((d) => x(d.t))
        .y0((d) => y(qLookup(d, b.lo)))
        .y1((d) => y(qLookup(d, b.hi)));
      root
        .append("path")
        .datum(quantilesAtStep)
        .attr("fill", "var(--info-fg)")
        .attr("fill-opacity", b.opacity)
        .attr("d", path);
    });

    const medianLine = d3
      .line<(typeof quantilesAtStep)[number]>()
      .x((d) => x(d.t))
      .y((d) => y(d.q50));
    root
      .append("path")
      .datum(quantilesAtStep)
      .attr("fill", "none")
      .attr("stroke", "var(--info-fg)")
      .attr("stroke-width", 1.5)
      .attr("d", medianLine);

    root
      .append("g")
      .attr("transform", `translate(0, ${innerH})`)
      .call(d3.axisBottom(x).ticks(6).tickFormat(d3.format("d")))
      .selectAll("text")
      .attr("fill", "var(--text-secondary)")
      .style("font-size", "10px");
    root
      .append("g")
      .call(d3.axisLeft(y).ticks(6).tickFormat(d3.format("$.2f")))
      .selectAll("text")
      .attr("fill", "var(--text-secondary)")
      .style("font-size", "10px");
  }, [paths]);

  return (
    <svg
      ref={ref}
      role="img"
      aria-label="Percentile fan"
      className={cn("h-full w-full", className)}
    />
  );
}

function qLookup(d: { q05: number; q10: number; q25: number; q75: number; q90: number; q95: number }, q: number): number {
  if (q === 0.05) return d.q05;
  if (q === 0.1) return d.q10;
  if (q === 0.25) return d.q25;
  if (q === 0.75) return d.q75;
  if (q === 0.9) return d.q90;
  return d.q95;
}
