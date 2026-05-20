import { useVirtualizer } from "@tanstack/react-virtual";
import { type CSSProperties, type ReactNode, useRef } from "react";

import { cn } from "@/lib/utils";

export interface ColumnDef<T> {
  key: string;
  header: ReactNode;
  width?: number;
  align?: "left" | "right" | "center";
  render: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  rows: T[];
  columns: ColumnDef<T>[];
  rowKey: (row: T, index: number) => string;
  onRowClick?: (row: T) => void;
  emptyState?: ReactNode;
  rowHeight?: number;
  className?: string;
}

/**
 * Lightweight virtualized table used everywhere except heavy data
 * grids that warrant AG Grid. Virtualization keeps live-updating
 * tables (paper runs, agent runs, monitor) responsive even with
 * 10k+ rows.
 */
export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  emptyState,
  rowHeight = 36,
  className,
}: DataTableProps<T>) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
  });

  const gridTemplate = columns
    .map((c) => (c.width ? `${c.width}px` : "minmax(0, 1fr)"))
    .join(" ");

  return (
    <div className={cn("flex h-full flex-col", className)}>
      <div
        className="grid border-b border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-2 text-[10px] uppercase tracking-wider text-[var(--text-secondary)]"
        style={{ gridTemplateColumns: gridTemplate }}
      >
        {columns.map((c) => (
          <span
            key={c.key}
            className={cn(
              c.align === "right" && "text-right",
              c.align === "center" && "text-center",
            )}
          >
            {c.header}
          </span>
        ))}
      </div>
      <div ref={parentRef} className="relative flex-1 overflow-auto">
        {rows.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 py-10 text-center text-sm text-[var(--text-secondary)]">
            {emptyState ?? "No data."}
          </div>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), width: "100%", position: "relative" }}>
            {virtualizer.getVirtualItems().map((vRow) => {
              const row = rows[vRow.index];
              if (!row) return null;
              const style: CSSProperties = {
                position: "absolute",
                top: vRow.start,
                width: "100%",
                height: vRow.size,
                gridTemplateColumns: gridTemplate,
              };
              return (
                <div
                  key={rowKey(row, vRow.index)}
                  style={style}
                  className={cn(
                    "grid items-center border-b border-[var(--border-subtle)] px-4 text-sm tabular",
                    onRowClick && "cursor-pointer hover:bg-[var(--bg-elevated)]",
                  )}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (e) => {
                          if (e.key === "Enter") onRowClick(row);
                        }
                      : undefined
                  }
                  tabIndex={onRowClick ? 0 : -1}
                  role={onRowClick ? "button" : "row"}
                >
                  {columns.map((c) => (
                    <span
                      key={c.key}
                      className={cn(
                        "truncate",
                        c.align === "right" && "text-right",
                        c.align === "center" && "text-center",
                      )}
                    >
                      {c.render(row)}
                    </span>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
