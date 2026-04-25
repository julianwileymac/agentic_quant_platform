"use client";

import type { CSSProperties } from "react";

export interface HeatmapCell {
  row: string;
  col: string;
  value: number;
}

interface HeatmapProps {
  cells: HeatmapCell[];
  rows: string[];
  cols: string[];
  min?: number;
  max?: number;
  cellSize?: number;
  format?: (n: number) => string;
}

const NEGATIVE = "#ef4444";
const POSITIVE = "#10b981";

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function colorFor(value: number, min: number, max: number) {
  if (value >= 0) {
    const t = max === 0 ? 0 : Math.min(1, value / max);
    const alpha = 0.15 + 0.6 * t;
    return `rgba(16,185,129,${alpha})`;
  }
  const t = min === 0 ? 0 : Math.min(1, value / min);
  const alpha = 0.15 + 0.6 * t;
  return `rgba(239,68,68,${alpha})`;
}

export function Heatmap({ cells, rows, cols, min, max, cellSize = 36, format }: HeatmapProps) {
  const values = cells.map((c) => c.value);
  const lo = min ?? Math.min(0, ...values);
  const hi = max ?? Math.max(0, ...values);
  const idx = new Map<string, number>();
  for (const c of cells) idx.set(`${c.row}|${c.col}`, c.value);

  const gridTemplate = `auto repeat(${cols.length}, ${cellSize}px)`;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: gridTemplate,
        gap: 2,
        fontSize: 11,
      }}
    >
      <div />
      {cols.map((c) => (
        <div key={`h-${c}`} style={{ textAlign: "center", padding: "4px 2px", opacity: 0.7 }}>
          {c}
        </div>
      ))}
      {rows.map((r) => (
        <Row key={r} row={r} cols={cols} idx={idx} lo={lo} hi={hi} cellSize={cellSize} format={format} />
      ))}
      <div />
      <div
        style={{
          gridColumn: `2 / span ${cols.length}`,
          marginTop: 8,
          height: 6,
          borderRadius: 3,
          background: `linear-gradient(to right, ${NEGATIVE}, #1f2937, ${POSITIVE})`,
        }}
      />
      <div />
      <div
        style={{
          gridColumn: `2 / span ${cols.length}`,
          display: "flex",
          justifyContent: "space-between",
          fontSize: 10,
          opacity: 0.6,
        }}
      >
        <span>{format ? format(lo) : lo.toFixed(2)}</span>
        <span>0</span>
        <span>{format ? format(hi) : hi.toFixed(2)}</span>
      </div>
    </div>
  );
}

interface RowProps {
  row: string;
  cols: string[];
  idx: Map<string, number>;
  lo: number;
  hi: number;
  cellSize: number;
  format?: (n: number) => string;
}

function Row({ row, cols, idx, lo, hi, cellSize, format }: RowProps) {
  return (
    <>
      <div style={{ padding: "0 8px", display: "flex", alignItems: "center", opacity: 0.7 }}>
        {row}
      </div>
      {cols.map((c) => {
        const value = idx.get(`${row}|${c}`);
        const style: CSSProperties = {
          height: cellSize,
          width: cellSize,
          borderRadius: 4,
          background: value === undefined ? "transparent" : colorFor(value, lo, hi),
          color: "var(--ant-color-text)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 10,
          fontVariantNumeric: "tabular-nums",
          border: value === undefined ? "1px dashed rgba(148,163,184,0.3)" : "none",
        };
        const lerped = value !== undefined && value < 0 ? value / lo : 0;
        return (
          <div key={`${row}-${c}`} style={style} title={value !== undefined ? `${row} × ${c}: ${value}` : ""}>
            {value === undefined ? "" : format ? format(value) : (Math.abs(value) < 1 ? value.toFixed(3) : Math.round(lerp(value, value, lerped)))}
          </div>
        );
      })}
    </>
  );
}
