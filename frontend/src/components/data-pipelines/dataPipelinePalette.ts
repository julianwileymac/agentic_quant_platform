import type { PaletteSection } from "@/components/flow/types";

/**
 * Data Pipeline Editor palette. Resolves to a manifest of the form
 * `{sources[], transforms[], features[], plan, sinks[]}`.
 */
export const DATA_PIPELINE_PALETTE: PaletteSection[] = [
  {
    title: "Sources",
    items: [
      {
        kind: "Template",
        label: "Loading template",
        description: "Run a curated backend loading workflow",
        accent: "#14b8a6",
        defaultParams: { template_id: "alpha-vantage-intraday-2y-all-active", overrides: {} },
      },
      {
        kind: "Source",
        label: "yfinance",
        accent: "#10b981",
        defaultParams: { provider: "yahoo", symbols: ["SPY", "AAPL"], interval: "1d" },
      },
      { kind: "Source", label: "Alpaca", accent: "#10b981", defaultParams: { provider: "alpaca" } },
      { kind: "Source", label: "IBKR Historical", accent: "#10b981", defaultParams: { provider: "ibkr" } },
      { kind: "Source", label: "FRED", accent: "#10b981", defaultParams: { provider: "fred" } },
    ],
  },
  {
    title: "Transforms",
    items: [
      { kind: "Transform", label: "Resample", accent: "#3b82f6", defaultParams: { interval: "1d" } },
      {
        kind: "Transform",
        label: "Adjust splits/dividends",
        accent: "#3b82f6",
        defaultParams: { kind: "adjust" },
      },
      {
        kind: "Transform",
        label: "Drop NA",
        accent: "#3b82f6",
        defaultParams: { kind: "dropna" },
      },
      {
        kind: "Dbt",
        label: "dbt build",
        description: "sink.dbt_build for selected models or tags",
        accent: "#ff694b",
        defaultParams: { select: ["tag:aqp_generated"] },
      },
    ],
  },
  {
    title: "Features",
    items: [
      { kind: "Feature", label: "SMA", accent: "#a855f7", defaultParams: { window: 20 } },
      { kind: "Feature", label: "RSI", accent: "#a855f7", defaultParams: { window: 14 } },
      { kind: "Feature", label: "Returns", accent: "#a855f7", defaultParams: { window: 1 } },
    ],
  },
  {
    title: "Execution",
    items: [
      { kind: "Plan", label: "Plan manifest", accent: "#0ea5e9", defaultParams: {} },
      { kind: "Load", label: "Load batch", accent: "#6366f1", defaultParams: { batch_size: 25 } },
    ],
  },
  {
    title: "Sinks",
    items: [
      {
        kind: "Iceberg",
        label: "Iceberg sink",
        accent: "#f59e0b",
        defaultParams: { namespace: "aqp", table: "" },
      },
      {
        kind: "Parquet",
        label: "Parquet sink",
        accent: "#f59e0b",
        defaultParams: { path: "data/parquet/" },
      },
      { kind: "Index", label: "Chroma index", accent: "#f59e0b", defaultParams: {} },
    ],
  },
];

export const DATA_PIPELINE_NODE_ACCENTS: Record<string, string> = {
  Template: "#14b8a6",
  Source: "#10b981",
  Transform: "#3b82f6",
  Dbt: "#ff694b",
  Feature: "#a855f7",
  Plan: "#0ea5e9",
  Load: "#6366f1",
  Iceberg: "#f59e0b",
  Parquet: "#f59e0b",
  Index: "#f59e0b",
};
