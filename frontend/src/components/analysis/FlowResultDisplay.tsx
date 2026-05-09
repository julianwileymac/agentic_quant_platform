import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { FlowResult } from "@/lib/analysis/api";

interface Props {
  result: FlowResult | null;
}

/**
 * Render a FlowResult inline:
 *  - metrics as a key/value grid;
 *  - a small Recharts line/bar when the rows look chart-able;
 *  - the rows themselves as a table preview.
 *
 * We deliberately don't auto-render the Plotly figure-dict — that
 * stays available in `result.chart` for a follow-up Plotly integration.
 */
export function FlowResultDisplay({ result }: Props) {
  if (!result) {
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        Run a flow to see the result inline.
      </p>
    );
  }
  const rows = result.rows ?? [];
  const metricEntries = Object.entries(result.metrics ?? {});
  const chartData = pickChart(rows);

  return (
    <div className="space-y-4">
      {result.error ? (
        <div className="rounded-md border border-[var(--neg-fg)] bg-[var(--bg-app)] p-3 text-xs text-[var(--neg-fg)]">
          {result.error}
        </div>
      ) : null}
      {metricEntries.length > 0 ? (
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase text-[var(--text-secondary)]">
            Metrics
          </h3>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
            {metricEntries.map(([key, value]) => (
              <div
                key={key}
                className="flex flex-col rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2"
              >
                <span className="text-[10px] text-[var(--text-secondary)]">{key}</span>
                <span className="font-mono text-sm text-[var(--text-primary)]">
                  {renderScalar(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {chartData ? (
        <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2">
          <h3 className="mb-1 text-xs font-medium uppercase text-[var(--text-secondary)]">
            {chartData.kind === "line" ? "Series preview" : "Bar preview"} ({chartData.x} vs {chartData.y})
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            {chartData.kind === "line" ? (
              <LineChart data={chartData.rows}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.2)" />
                <XAxis
                  dataKey={chartData.x}
                  fontSize={11}
                  stroke="var(--text-secondary)"
                />
                <YAxis fontSize={11} stroke="var(--text-secondary)" />
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-elevated)",
                    borderColor: "var(--border-default)",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey={chartData.y}
                  stroke="#3B82F6"
                  dot={false}
                  strokeWidth={1.5}
                />
              </LineChart>
            ) : (
              <BarChart data={chartData.rows}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.2)" />
                <XAxis
                  dataKey={chartData.x}
                  fontSize={11}
                  stroke="var(--text-secondary)"
                />
                <YAxis fontSize={11} stroke="var(--text-secondary)" />
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-elevated)",
                    borderColor: "var(--border-default)",
                  }}
                />
                <Bar dataKey={chartData.y} fill="#3B82F6" />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      ) : null}
      {rows.length > 0 ? (
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase text-[var(--text-secondary)]">
            Rows ({rows.length} preview)
          </h3>
          <div className="max-h-[320px] overflow-auto rounded-md border border-[var(--border-default)]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[var(--bg-elevated)]">
                <tr>
                  {Object.keys(rows[0]!).map((col) => (
                    <th
                      key={col}
                      className="border-b border-[var(--border-default)] px-2 py-1 text-left font-medium"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 100).map((row, idx) => (
                  <tr
                    key={idx}
                    className="border-b border-[var(--border-default)] last:border-0"
                  >
                    {Object.keys(rows[0]!).map((col) => (
                      <td key={col} className="px-2 py-1 font-mono">
                        {renderScalar(row[col])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function renderScalar(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    if (Math.abs(value) < 1e-4 || Math.abs(value) >= 1e7) {
      return value.toExponential(4);
    }
    return value.toFixed(Math.abs(value) >= 100 ? 2 : 6);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function pickChart(rows: Array<Record<string, unknown>>):
  | { kind: "line" | "bar"; x: string; y: string; rows: Array<Record<string, unknown>> }
  | null {
  if (rows.length < 2) return null;
  const sample = rows[0]!;
  const numeric: string[] = [];
  let timestampCol: string | null = null;
  let stringCol: string | null = null;
  for (const [key, value] of Object.entries(sample)) {
    if (typeof value === "number" && Number.isFinite(value)) numeric.push(key);
    else if (typeof value === "string") {
      if (
        !timestampCol &&
        (key.toLowerCase().includes("time") ||
          key.toLowerCase().includes("date") ||
          /\d{4}-\d{2}-\d{2}/.test(value))
      ) {
        timestampCol = key;
      }
      if (!stringCol) stringCol = key;
    }
  }
  const y = numeric[0];
  if (!y) return null;
  if (timestampCol)
    return { kind: "line", x: timestampCol, y, rows };
  // Use the first index-like or string-like column
  const x = stringCol ?? numeric[1] ?? null;
  if (!x) return null;
  return { kind: "bar", x, y, rows };
}
