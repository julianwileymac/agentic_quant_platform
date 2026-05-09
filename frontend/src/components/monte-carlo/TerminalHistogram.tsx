import * as d3 from "d3";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

interface HistogramProps {
  /** Final-step values (1 per simulated path). */
  values: number[];
  bins?: number;
  className?: string;
}

/**
 * D3 histogram over terminal values from a Monte Carlo simulation.
 */
export function TerminalHistogram({ values, bins = 36, className }: HistogramProps) {
  const ref = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    if (values.length === 0) {
      d3.select(svg).selectAll("*").remove();
      return;
    }
    const rect = svg.getBoundingClientRect();
    const width = Math.max(rect.width || 600, 320);
    const height = Math.max(rect.height || 200, 160);
    const margin = { top: 8, right: 20, bottom: 28, left: 50 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const x = d3
      .scaleLinear()
      .domain([d3.min(values) ?? 0, d3.max(values) ?? 1])
      .nice()
      .range([0, innerW]);
    const histogram = d3
      .bin<number, number>()
      .domain(x.domain() as [number, number])
      .thresholds(x.ticks(bins));
    const groups = histogram(values);
    const y = d3
      .scaleLinear()
      .domain([0, d3.max(groups, (g) => g.length) ?? 1])
      .range([innerH, 0]);

    d3.select(svg).selectAll("*").remove();
    const root = d3
      .select(svg)
      .attr("viewBox", `0 0 ${width} ${height}`)
      .append("g")
      .attr("transform", `translate(${margin.left}, ${margin.top})`);

    root
      .selectAll("rect")
      .data(groups)
      .join("rect")
      .attr("x", (g) => x(g.x0 ?? 0))
      .attr("y", (g) => y(g.length))
      .attr("width", (g) => Math.max(0, x(g.x1 ?? 0) - x(g.x0 ?? 0) - 1))
      .attr("height", (g) => innerH - y(g.length))
      .attr("fill", "var(--info-fg)")
      .attr("fill-opacity", 0.65);

    root
      .append("g")
      .attr("transform", `translate(0, ${innerH})`)
      .call(d3.axisBottom(x).ticks(6).tickFormat(d3.format("$.2f")))
      .selectAll("text")
      .attr("fill", "var(--text-secondary)")
      .style("font-size", "10px");
    root
      .append("g")
      .call(d3.axisLeft(y).ticks(5))
      .selectAll("text")
      .attr("fill", "var(--text-secondary)")
      .style("font-size", "10px");
  }, [values, bins]);

  return (
    <svg
      ref={ref}
      role="img"
      aria-label="Terminal value histogram"
      className={cn("h-full w-full", className)}
    />
  );
}
