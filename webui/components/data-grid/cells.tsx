"use client";

import { Tag } from "antd";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import type { ICellRendererParams, ValueFormatterParams } from "ag-grid-community";

dayjs.extend(relativeTime);

const STATUS_COLORS: Record<string, string> = {
  ok: "green",
  healthy: "green",
  online: "green",
  active: "green",
  completed: "green",
  succeeded: "green",
  running: "blue",
  pending: "blue",
  queued: "geekblue",
  starting: "geekblue",
  paused: "orange",
  warning: "orange",
  failed: "red",
  error: "red",
  cancelled: "default",
  stopped: "default",
};

export function StatusBadgeCell(params: ICellRendererParams) {
  const value = String(params.value ?? "").toLowerCase();
  if (!value) return <span>—</span>;
  return <Tag color={STATUS_COLORS[value] ?? "default"}>{params.value}</Tag>;
}

export function TagListCell(params: ICellRendererParams<unknown, string[] | string>) {
  const value = params.value;
  const items = Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value.split(",").map((s) => s.trim()).filter(Boolean)
      : [];
  if (items.length === 0) return <span style={{ opacity: 0.5 }}>—</span>;
  return (
    <span>
      {items.slice(0, 4).map((t) => (
        <Tag key={t}>{t}</Tag>
      ))}
      {items.length > 4 ? <span style={{ opacity: 0.6 }}>+{items.length - 4}</span> : null}
    </span>
  );
}

export function NumberCellFormatter(params: ValueFormatterParams) {
  const value = params.value;
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function PercentCellFormatter(params: ValueFormatterParams) {
  const value = params.value;
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return `${(n * 100).toFixed(2)}%`;
}

export function CurrencyCellFormatter(params: ValueFormatterParams) {
  const value = params.value;
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

export function DateTimeCellFormatter(params: ValueFormatterParams) {
  const value = params.value;
  if (!value) return "—";
  const d = dayjs(value as string);
  return d.isValid() ? d.format("YYYY-MM-DD HH:mm") : String(value);
}

export function RelativeTimeCellFormatter(params: ValueFormatterParams) {
  const value = params.value;
  if (!value) return "—";
  const d = dayjs(value as string);
  return d.isValid() ? d.fromNow() : String(value);
}

export function PnlCell(params: ICellRendererParams<unknown, number>) {
  const value = params.value;
  if (value === null || value === undefined) return <span>—</span>;
  const n = Number(value);
  if (Number.isNaN(n)) return <span>{String(value)}</span>;
  const color = n > 0 ? "#10b981" : n < 0 ? "#ef4444" : "var(--ant-color-text)";
  return (
    <span style={{ color, fontVariantNumeric: "tabular-nums" }}>
      {n > 0 ? "+" : ""}
      {n.toLocaleString(undefined, { maximumFractionDigits: 4 })}
    </span>
  );
}
