import type { ColDef } from "ag-grid-community";

import type {
  BacktestRunSummary,
  CrewRunSummary,
  DataSourceSummary,
  FillRow,
  LedgerEntryRow,
  MlModelSummary,
  OrderRow,
  PaperRunSummary,
  PositionRow,
  StrategySummary,
} from "@/lib/api/domains";

import {
  CurrencyCellFormatter,
  DateTimeCellFormatter,
  NumberCellFormatter,
  PercentCellFormatter,
  PnlCell,
  RelativeTimeCellFormatter,
  StatusBadgeCell,
  TagListCell,
} from "./cells";

export const strategyColumns: ColDef<StrategySummary>[] = [
  { field: "name", headerName: "Strategy", flex: 2, minWidth: 220 },
  {
    field: "status",
    headerName: "Status",
    cellRenderer: StatusBadgeCell,
    width: 130,
  },
  { field: "asset_class", headerName: "Asset class", width: 140 },
  { field: "tags", headerName: "Tags", cellRenderer: TagListCell, flex: 2, minWidth: 180 },
  { field: "latest_version", headerName: "Latest version", width: 150 },
  {
    field: "updated_at",
    headerName: "Updated",
    valueFormatter: RelativeTimeCellFormatter,
    width: 160,
  },
];

export const backtestColumns: ColDef<BacktestRunSummary>[] = [
  { field: "id", headerName: "Run", flex: 2, minWidth: 200 },
  { field: "engine", headerName: "Engine", width: 130 },
  {
    field: "status",
    headerName: "Status",
    cellRenderer: StatusBadgeCell,
    width: 130,
  },
  {
    field: "started_at",
    headerName: "Started",
    valueFormatter: DateTimeCellFormatter,
    width: 170,
  },
  {
    field: "finished_at",
    headerName: "Finished",
    valueFormatter: DateTimeCellFormatter,
    width: 170,
  },
  {
    headerName: "Sharpe",
    valueGetter: ({ data }) => data?.metrics?.sharpe ?? null,
    valueFormatter: NumberCellFormatter,
    width: 110,
  },
  {
    headerName: "CAGR",
    valueGetter: ({ data }) => data?.metrics?.cagr ?? null,
    valueFormatter: PercentCellFormatter,
    width: 110,
  },
  {
    headerName: "Max DD",
    valueGetter: ({ data }) => data?.metrics?.max_drawdown ?? null,
    valueFormatter: PercentCellFormatter,
    width: 120,
  },
];

export const paperRunColumns: ColDef<PaperRunSummary>[] = [
  { field: "id", headerName: "Run", flex: 2, minWidth: 200 },
  {
    field: "status",
    headerName: "Status",
    cellRenderer: StatusBadgeCell,
    width: 130,
  },
  { field: "config_path", headerName: "Config", flex: 2, minWidth: 180 },
  {
    field: "started_at",
    headerName: "Started",
    valueFormatter: DateTimeCellFormatter,
    width: 170,
  },
  {
    field: "stopped_at",
    headerName: "Stopped",
    valueFormatter: DateTimeCellFormatter,
    width: 170,
  },
];

export const orderColumns: ColDef<OrderRow>[] = [
  { field: "id", headerName: "Order ID", flex: 2, minWidth: 180 },
  { field: "vt_symbol", headerName: "Symbol", width: 140 },
  { field: "side", headerName: "Side", width: 100, cellRenderer: StatusBadgeCell },
  { field: "quantity", headerName: "Qty", valueFormatter: NumberCellFormatter, width: 110 },
  { field: "filled", headerName: "Filled", valueFormatter: NumberCellFormatter, width: 110 },
  {
    field: "avg_fill_price",
    headerName: "Avg fill",
    valueFormatter: CurrencyCellFormatter,
    width: 130,
  },
  { field: "status", headerName: "Status", cellRenderer: StatusBadgeCell, width: 130 },
  { field: "venue", headerName: "Venue", width: 110 },
  {
    field: "submitted_at",
    headerName: "Submitted",
    valueFormatter: DateTimeCellFormatter,
    width: 170,
  },
];

export const fillColumns: ColDef<FillRow>[] = [
  { field: "id", headerName: "Fill", flex: 1, minWidth: 160 },
  { field: "order_id", headerName: "Order", flex: 1, minWidth: 160 },
  { field: "vt_symbol", headerName: "Symbol", width: 140 },
  { field: "price", headerName: "Price", valueFormatter: CurrencyCellFormatter, width: 130 },
  { field: "quantity", headerName: "Qty", valueFormatter: NumberCellFormatter, width: 110 },
  { field: "venue", headerName: "Venue", width: 110 },
  {
    field: "timestamp",
    headerName: "When",
    valueFormatter: DateTimeCellFormatter,
    width: 170,
  },
];

export const positionColumns: ColDef<PositionRow>[] = [
  { field: "vt_symbol", headerName: "Symbol", width: 160 },
  { field: "quantity", headerName: "Qty", valueFormatter: NumberCellFormatter, width: 110 },
  {
    field: "avg_price",
    headerName: "Avg cost",
    valueFormatter: CurrencyCellFormatter,
    width: 130,
  },
  {
    field: "last_price",
    headerName: "Last",
    valueFormatter: CurrencyCellFormatter,
    width: 130,
  },
  {
    field: "market_value",
    headerName: "Market value",
    valueFormatter: CurrencyCellFormatter,
    width: 150,
  },
  {
    field: "unrealized_pnl",
    headerName: "Unrealized PnL",
    cellRenderer: PnlCell,
    width: 160,
  },
];

export const ledgerColumns: ColDef<LedgerEntryRow>[] = [
  {
    field: "timestamp",
    headerName: "When",
    valueFormatter: DateTimeCellFormatter,
    width: 170,
  },
  { field: "account", headerName: "Account", width: 140 },
  { field: "type", headerName: "Type", cellRenderer: StatusBadgeCell, width: 130 },
  {
    field: "amount",
    headerName: "Amount",
    cellRenderer: PnlCell,
    width: 140,
  },
  {
    field: "balance_after",
    headerName: "Balance",
    valueFormatter: CurrencyCellFormatter,
    width: 140,
  },
  { field: "description", headerName: "Description", flex: 2, minWidth: 200 },
];

export const dataSourceColumns: ColDef<DataSourceSummary>[] = [
  { field: "name", headerName: "Source", flex: 2, minWidth: 200 },
  { field: "vendor", headerName: "Vendor", width: 140 },
  {
    field: "status",
    headerName: "Status",
    cellRenderer: StatusBadgeCell,
    width: 130,
  },
  { field: "description", headerName: "Description", flex: 3, minWidth: 240 },
];

export const crewRunColumns: ColDef<CrewRunSummary>[] = [
  { field: "task_id", headerName: "Task", flex: 2, minWidth: 220 },
  { field: "crew", headerName: "Crew", width: 160 },
  { field: "status", headerName: "Status", cellRenderer: StatusBadgeCell, width: 130 },
  {
    field: "started_at",
    headerName: "Started",
    valueFormatter: DateTimeCellFormatter,
    width: 170,
  },
  {
    field: "finished_at",
    headerName: "Finished",
    valueFormatter: DateTimeCellFormatter,
    width: 170,
  },
];

export const mlModelColumns: ColDef<MlModelSummary>[] = [
  { field: "name", headerName: "Model", flex: 2, minWidth: 220 },
  { field: "framework", headerName: "Framework", width: 140 },
  { field: "status", headerName: "Status", cellRenderer: StatusBadgeCell, width: 130 },
  {
    headerName: "Accuracy",
    valueGetter: ({ data }) => data?.metrics?.accuracy ?? null,
    valueFormatter: PercentCellFormatter,
    width: 120,
  },
  {
    headerName: "RMSE",
    valueGetter: ({ data }) => data?.metrics?.rmse ?? null,
    valueFormatter: NumberCellFormatter,
    width: 120,
  },
];
