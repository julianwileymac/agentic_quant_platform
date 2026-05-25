"use client";

import { Check, Minus, X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { MotionInView } from "./MotionInView";

interface ComparisonColumn {
  /** Column heading (e.g. "Cloud", "Self-Hosted"). */
  name: string;
  /** Optional sub-heading. */
  tagline?: string;
  /** Highlight column (e.g. recommended). */
  highlight?: boolean;
}

/**
 * Cell value: `true` = check, `false` = X, `"-"` = dash, string = custom text,
 * ReactNode = arbitrary content (e.g. tier name).
 */
export type ComparisonCell = boolean | "-" | string | ReactNode;

interface ComparisonRow {
  /** Row label. */
  label: string;
  /** Optional row group heading. */
  group?: string;
  /** Cells aligned with `columns`. */
  cells: ComparisonCell[];
}

interface ComparisonTableProps {
  columns: ComparisonColumn[];
  rows: ComparisonRow[];
  className?: string;
}

function renderCell(cell: ComparisonCell): ReactNode {
  if (cell === true) {
    return (
      <Check
        size={18}
        className="mx-auto"
        style={{ color: "var(--pos-fg)" }}
      />
    );
  }
  if (cell === false) {
    return (
      <X
        size={18}
        className="mx-auto"
        style={{ color: "var(--text-muted)" }}
      />
    );
  }
  if (cell === "-") {
    return (
      <Minus
        size={14}
        className="mx-auto"
        style={{ color: "var(--text-muted)" }}
      />
    );
  }
  return (
    <span
      className="text-sm"
      style={{ color: "var(--text-primary)" }}
    >
      {cell}
    </span>
  );
}

export function ComparisonTable({
  columns,
  rows,
  className,
}: ComparisonTableProps) {
  return (
    <MotionInView from="up">
      <div
        className={cn(
          "overflow-hidden rounded-xl",
          className,
        )}
        style={{
          background: "var(--glass-bg)",
          border: "1px solid var(--glass-border)",
          backdropFilter: "blur(var(--glass-blur))",
        }}
      >
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr
                className="border-b"
                style={{ borderColor: "var(--border-default)" }}
              >
                <th
                  className="px-6 py-5 text-left text-sm font-semibold"
                  style={{ color: "var(--text-muted)" }}
                >
                  Feature
                </th>
                {columns.map((col) => (
                  <th
                    key={col.name}
                    className="px-6 py-5 text-center"
                    style={
                      col.highlight
                        ? {
                            background: "rgba(22,119,255,0.06)",
                          }
                        : undefined
                    }
                  >
                    <div
                      className="text-base font-bold"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {col.name}
                    </div>
                    {col.tagline ? (
                      <div
                        className="mt-1 text-xs font-normal"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {col.tagline}
                      </div>
                    ) : null}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIdx) => {
                const showGroup =
                  row.group && (rowIdx === 0 || rows[rowIdx - 1].group !== row.group);
                return (
                  <>
                    {showGroup ? (
                      <tr
                        key={`group-${row.group}`}
                        style={{
                          background: "rgba(255,255,255,0.02)",
                        }}
                      >
                        <td
                          colSpan={columns.length + 1}
                          className="px-6 py-3 text-xs font-bold uppercase tracking-wider"
                          style={{ color: "var(--accent-primary)" }}
                        >
                          {row.group}
                        </td>
                      </tr>
                    ) : null}
                    <tr
                      key={row.label}
                      className="border-t"
                      style={{ borderColor: "var(--border-default)" }}
                    >
                      <td
                        className="px-6 py-4 text-sm"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {row.label}
                      </td>
                      {row.cells.map((cell, cellIdx) => (
                        <td
                          // biome-ignore lint/suspicious/noArrayIndexKey: cells are positional
                          key={cellIdx}
                          className="px-6 py-4 text-center"
                          style={
                            columns[cellIdx]?.highlight
                              ? {
                                  background: "rgba(22,119,255,0.04)",
                                }
                              : undefined
                          }
                        >
                          {renderCell(cell)}
                        </td>
                      ))}
                    </tr>
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </MotionInView>
  );
}
