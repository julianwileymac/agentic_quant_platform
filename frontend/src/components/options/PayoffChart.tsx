import * as d3 from "d3";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

interface PayoffChartProps {
  forward: number;
  strike: number;
  isCall: boolean;
  /** Optional premium paid; subtracts from payoff to render P&L instead of pure intrinsic. */
  premium?: number;
  /** Width range around the strike, in % of strike. Default ±50 %. */
  widthPct?: number;
  className?: string;
}

/**
 * D3 payoff diagram for a vanilla European option at expiry. Imperative
 * D3 (no Recharts) so the chart matches the EquityChart pattern used
 * elsewhere and stays performant on dense option chains.
 */
export function PayoffChart({
  forward,
  strike,
  isCall,
  premium = 0,
  widthPct = 0.5,
  className,
}: PayoffChartProps) {
  const ref = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const width = Math.max(rect.width || 600, 320);
    const height = Math.max(rect.height || 240, 180);
    const margin = { top: 14, right: 28, bottom: 28, left: 56 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const lo = strike * (1 - widthPct);
    const hi = strike * (1 + widthPct);
    const xs = d3.range(lo, hi + (hi - lo) / 100, (hi - lo) / 200);
    const intrinsic = (s: number) =>
      isCall ? Math.max(s - strike, 0) : Math.max(strike - s, 0);
    const payoff = xs.map((s) => ({ s, y: intrinsic(s) - premium }));

    const yMin = Math.min(...payoff.map((p) => p.y));
    const yMax = Math.max(...payoff.map((p) => p.y));
    const yPad = (yMax - yMin) * 0.1 || 1;

    const x = d3.scaleLinear().domain([lo, hi]).range([0, innerW]);
    const y = d3
      .scaleLinear()
      .domain([yMin - yPad, yMax + yPad])
      .nice()
      .range([innerH, 0]);

    d3.select(svg).selectAll("*").remove();
    const root = d3
      .select(svg)
      .attr("viewBox", `0 0 ${width} ${height}`)
      .append("g")
      .attr("transform", `translate(${margin.left}, ${margin.top})`);

    root.append("rect").attr("width", innerW).attr("height", innerH).attr("fill", "transparent");

    // axes
    root
      .append("g")
      .attr("transform", `translate(0, ${innerH})`)
      .call(d3.axisBottom(x).ticks(6).tickFormat(d3.format("$.2f")))
      .selectAll("text")
      .attr("fill", "var(--text-secondary)")
      .style("font-size", "10px");
    root
      .append("g")
      .call(d3.axisLeft(y).ticks(6).tickFormat(d3.format("+$.2f")))
      .selectAll("text")
      .attr("fill", "var(--text-secondary)")
      .style("font-size", "10px");

    // zero line
    root
      .append("line")
      .attr("x1", 0)
      .attr("x2", innerW)
      .attr("y1", y(0))
      .attr("y2", y(0))
      .attr("stroke", "var(--border-subtle)")
      .attr("stroke-dasharray", "2 4");

    // strike marker
    root
      .append("line")
      .attr("x1", x(strike))
      .attr("x2", x(strike))
      .attr("y1", 0)
      .attr("y2", innerH)
      .attr("stroke", "var(--info-fg)")
      .attr("stroke-dasharray", "3 3")
      .attr("stroke-opacity", 0.55);
    root
      .append("text")
      .attr("x", x(strike) + 4)
      .attr("y", 12)
      .attr("fill", "var(--info-fg)")
      .style("font-size", "10px")
      .text(`K = ${strike.toFixed(2)}`);

    // forward marker
    if (forward >= lo && forward <= hi) {
      root
        .append("line")
        .attr("x1", x(forward))
        .attr("x2", x(forward))
        .attr("y1", 0)
        .attr("y2", innerH)
        .attr("stroke", "var(--text-secondary)")
        .attr("stroke-dasharray", "1 3");
      root
        .append("text")
        .attr("x", x(forward) + 4)
        .attr("y", innerH - 4)
        .attr("fill", "var(--text-secondary)")
        .style("font-size", "10px")
        .text(`F = ${forward.toFixed(2)}`);
    }

    // gradient: green above zero, red below
    const defs = d3.select(svg).append("defs");
    const grad = defs
      .append("linearGradient")
      .attr("id", "payoff-grad")
      .attr("x1", "0")
      .attr("x2", "0")
      .attr("y1", "0")
      .attr("y2", "1");
    grad.append("stop").attr("offset", 0).attr("stop-color", "var(--pos-fg)").attr("stop-opacity", 0.85);
    grad
      .append("stop")
      .attr("offset", `${(y(0) / innerH) * 100}%`)
      .attr("stop-color", "var(--pos-fg)")
      .attr("stop-opacity", 0.85);
    grad
      .append("stop")
      .attr("offset", `${(y(0) / innerH) * 100}%`)
      .attr("stop-color", "var(--neg-fg)")
      .attr("stop-opacity", 0.85);
    grad.append("stop").attr("offset", 1).attr("stop-color", "var(--neg-fg)").attr("stop-opacity", 0.85);

    const line = d3
      .line<{ s: number; y: number }>()
      .x((d) => x(d.s))
      .y((d) => y(d.y));

    root
      .append("path")
      .datum(payoff)
      .attr("fill", "none")
      .attr("stroke", "url(#payoff-grad)")
      .attr("stroke-width", 2)
      .attr("d", line);
  }, [forward, strike, isCall, premium, widthPct]);

  return (
    <svg
      ref={ref}
      role="img"
      aria-label="Option payoff at expiry"
      className={cn("h-full w-full", className)}
    />
  );
}
