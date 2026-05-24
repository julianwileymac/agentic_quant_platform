import "ag-grid-community/styles/ag-grid.css";

import { AgGridReact } from "ag-grid-react";
import type {
  CellClassParams,
  ColDef,
} from "ag-grid-community";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";

/**
 * Generic Arrow-frame viewer backed by AG Grid v32 community.
 *
 * Reused by:
 *
 * - The EDA cell preview when a cell returns a tabular value
 *   (``data.duckdb_sql`` / ``data.iceberg_scan`` outputs).
 * - The Evaluation Trials panel where each row is one sweep trial.
 * - The Run-history drawer when expanding a node's ``output_locator``
 *   into a row preview.
 *
 * Frame shape is intentionally permissive:
 *
 *   ``{ columns: string[], rows: Array<Record<string, unknown>> | unknown[][] }``
 *
 * — either an array of column-keyed dicts (the natural pandas form)
 * or an array of positional rows (the natural Arrow form). Internally
 * we normalize to the dict form so AG Grid's ``rowData`` contract
 * stays simple.
 *
 * Wraps with ``.ag-theme-aqp-dark`` so the styling matches the dark
 * theme defined in ``src/styles/tokens.css``. Phase 1 ships sortable,
 * filterable, resizable columns + tabular-figure numeric rendering so
 * trader-facing surfaces never shift width when a digit updates.
 */
export interface FramePayload {
  columns: string[];
  rows: Array<Record<string, unknown>> | unknown[][];
  schema?: Record<string, string>;
  total_rows?: number;
}

interface EdaFrameViewerProps {
  frame: FramePayload | null | undefined;
  caption?: string;
  /** Max rows rendered into AG Grid; defaults to 5000. */
  maxRows?: number;
  /** AG Grid height (must be a CSS dimension). Defaults to ``"100%"``. */
  height?: string | number;
}

const DEFAULT_MAX_ROWS = 5000;

function normalizeRows(
  rows: FramePayload["rows"],
  columns: string[],
): Array<Record<string, unknown>> {
  if (!rows.length) return [];
  if (Array.isArray(rows[0])) {
    return (rows as unknown[][]).map((row) => {
      const dict: Record<string, unknown> = {};
      for (let i = 0; i < columns.length; i++) {
        dict[columns[i] ?? `c${i}`] = row[i];
      }
      return dict;
    });
  }
  return rows as Array<Record<string, unknown>>;
}

function inferNumeric(value: unknown): boolean {
  if (typeof value === "number") return true;
  if (typeof value === "string" && value !== "") {
    const n = Number(value);
    return Number.isFinite(n);
  }
  return false;
}

function fmtNumeric(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return String(value);
  if (Math.abs(num) >= 1e6 || (Math.abs(num) < 1e-3 && num !== 0)) {
    return num.toExponential(3);
  }
  return num.toLocaleString(undefined, {
    maximumFractionDigits: 4,
    minimumFractionDigits: 0,
  });
}

export function EdaFrameViewer({
  frame,
  caption,
  maxRows = DEFAULT_MAX_ROWS,
  height = "100%",
}: EdaFrameViewerProps) {
  const rowData = useMemo(() => {
    if (!frame) return [];
    const normalised = normalizeRows(frame.rows, frame.columns);
    return normalised.slice(0, maxRows);
  }, [frame, maxRows]);

  const columnDefs: ColDef[] = useMemo(() => {
    if (!frame) return [];
    return frame.columns.map((col) => {
      const sample = rowData.find((row) => row[col] !== null && row[col] !== undefined);
      const numeric = sample !== undefined && inferNumeric(sample[col]);
      return {
        field: col,
        headerName: col,
        sortable: true,
        filter: numeric ? "agNumberColumnFilter" : "agTextColumnFilter",
        resizable: true,
        cellClass: numeric ? "ag-right-aligned-cell font-variant-numeric-tabular" : undefined,
        valueFormatter: numeric
          ? (params: CellClassParams) => fmtNumeric(params.value)
          : undefined,
      } satisfies ColDef;
    });
  }, [frame, rowData]);

  if (!frame || !frame.columns?.length) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
        No frame yet. Run a cell that returns a DataFrame or Arrow table.
      </div>
    );
  }

  const truncated =
    typeof frame.total_rows === "number" && frame.total_rows > rowData.length;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="outline">
          {rowData.length.toLocaleString()} rows × {frame.columns.length} cols
        </Badge>
        {truncated ? (
          <Badge variant="warn" title={`Total rows: ${frame.total_rows}`}>
            preview only (max {maxRows.toLocaleString()})
          </Badge>
        ) : null}
        {caption ? <span className="truncate">{caption}</span> : null}
      </div>
      <div className="ag-theme-aqp-dark min-h-0 flex-1" style={{ height }}>
        <AgGridReact
          rowData={rowData}
          columnDefs={columnDefs}
          defaultColDef={{
            minWidth: 80,
            flex: 1,
          }}
          animateRows={true}
          headerHeight={36}
          rowHeight={32}
          tooltipShowDelay={400}
          suppressCellFocus={true}
          enableCellTextSelection={true}
        />
      </div>
    </div>
  );
}

export default EdaFrameViewer;
