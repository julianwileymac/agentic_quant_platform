"use client";

import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";

import type {
  ColDef,
  GridOptions,
  GridReadyEvent,
  RowClickedEvent,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useEffect, useMemo, useRef } from "react";

import { useUiStore } from "@/lib/store/ui";

// AG Grid Community 32.x auto-registers community modules; 33+ requires
// explicit registration via `ModuleRegistry.registerModules([...])`. Keep
// this import-only file working across both: when we move to 33+, swap in
// the explicit registration here.

export interface DataGridProps<T> {
  rowData: T[] | null | undefined;
  columnDefs: ColDef<T>[];
  loading?: boolean;
  height?: number | string;
  density?: "compact" | "comfortable";
  pagination?: boolean;
  paginationPageSize?: number;
  quickFilterText?: string;
  onRowClicked?: (row: T) => void;
  getRowId?: (row: T) => string;
  emptyMessage?: string;
  className?: string;
  rowSelection?: "single" | "multiple";
  defaultColDef?: ColDef<T>;
  gridOptions?: GridOptions<T>;
}

export function DataGrid<T extends object>(props: DataGridProps<T>) {
  const {
    rowData,
    columnDefs,
    loading,
    height = 480,
    density = "comfortable",
    pagination = true,
    paginationPageSize = 25,
    quickFilterText,
    onRowClicked,
    getRowId,
    emptyMessage = "No rows to display",
    className,
    rowSelection,
    defaultColDef,
    gridOptions,
  } = props;

  const themeMode = useUiStore((s) => s.themeMode);
  const themeClass =
    themeMode === "dark" ? "ag-theme-quartz-dark" : "ag-theme-quartz";

  const gridRef = useRef<AgGridReact<T>>(null);

  const mergedDefaultColDef = useMemo<ColDef<T>>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
      flex: 1,
      minWidth: 110,
      ...defaultColDef,
    }),
    [defaultColDef],
  );

  useEffect(() => {
    gridRef.current?.api?.setGridOption("quickFilterText", quickFilterText ?? "");
  }, [quickFilterText]);

  useEffect(() => {
    if (loading) {
      gridRef.current?.api?.showLoadingOverlay();
    } else if (rowData && rowData.length === 0) {
      gridRef.current?.api?.showNoRowsOverlay();
    } else {
      gridRef.current?.api?.hideOverlay();
    }
  }, [loading, rowData]);

  const onGridReady = (e: GridReadyEvent<T>) => {
    if (loading) e.api.showLoadingOverlay();
  };

  const rowHeight = density === "compact" ? 30 : 36;

  return (
    <div
      className={[themeClass, className].filter(Boolean).join(" ")}
      style={{
        height,
        width: "100%",
      }}
    >
      <AgGridReact<T>
        ref={gridRef}
        rowData={rowData ?? []}
        columnDefs={columnDefs}
        defaultColDef={mergedDefaultColDef}
        animateRows
        rowHeight={rowHeight}
        headerHeight={36}
        pagination={pagination}
        paginationPageSize={paginationPageSize}
        paginationPageSizeSelector={[10, 25, 50, 100]}
        suppressCellFocus
        getRowId={getRowId ? (params) => getRowId(params.data) : undefined}
        rowSelection={rowSelection}
        onRowClicked={(e: RowClickedEvent<T>) => {
          if (e.data) onRowClicked?.(e.data);
        }}
        onGridReady={onGridReady}
        overlayNoRowsTemplate={`<div style="padding:24px;color:#94a3b8;">${emptyMessage}</div>`}
        overlayLoadingTemplate={`<div style="padding:24px;color:#94a3b8;">Loading…</div>`}
        {...gridOptions}
      />
    </div>
  );
}
