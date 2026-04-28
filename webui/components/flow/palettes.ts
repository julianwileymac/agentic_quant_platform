import type { PaletteSection } from "./types";

export const AGENT_PALETTE: PaletteSection[] = [
  {
    title: "LLM",
    items: [
      {
        kind: "LLM",
        label: "Quick model",
        description: "Fast, low-cost completions",
        accent: "#10b981",
        defaultParams: { tier: "quick", temperature: 0.4 },
      },
      {
        kind: "LLM",
        label: "Deep model",
        description: "Reasoning-heavy completions",
        accent: "#10b981",
        defaultParams: { tier: "deep", temperature: 0.2 },
      },
    ],
  },
  {
    title: "Memory",
    items: [
      {
        kind: "Memory",
        label: "Conversation memory",
        accent: "#a855f7",
        defaultParams: { kind: "conversation" },
      },
      {
        kind: "Memory",
        label: "Vector memory (Chroma)",
        accent: "#a855f7",
        defaultParams: { kind: "vector", store: "chroma" },
      },
    ],
  },
  {
    title: "Tools",
    items: [
      {
        kind: "Tool",
        label: "Backtest tool",
        description: "POST /backtest/run",
        accent: "#3b82f6",
        defaultParams: { tool: "backtest_run" },
      },
      {
        kind: "Tool",
        label: "Data lookup",
        description: "GET /data/{vt_symbol}/bars",
        accent: "#3b82f6",
        defaultParams: { tool: "data_lookup" },
      },
      {
        kind: "Tool",
        label: "Web search",
        accent: "#3b82f6",
        defaultParams: { tool: "web_search" },
      },
    ],
  },
  {
    title: "Agents",
    items: [
      {
        kind: "Agent",
        label: "Researcher",
        accent: "#f59e0b",
        defaultParams: { role: "researcher" },
      },
      {
        kind: "Agent",
        label: "Analyst",
        accent: "#f59e0b",
        defaultParams: { role: "analyst" },
      },
      {
        kind: "Agent",
        label: "Trader",
        accent: "#f59e0b",
        defaultParams: { role: "trader" },
      },
    ],
  },
  {
    title: "Tasks",
    items: [
      { kind: "Task", label: "Task", accent: "#8b5cf6", defaultParams: { description: "" } },
      { kind: "Output", label: "Output", accent: "#ef4444", defaultParams: {} },
    ],
  },
];

export const DATA_PALETTE: PaletteSection[] = [
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
      {
        kind: "Source",
        label: "Alpaca",
        accent: "#10b981",
        defaultParams: { provider: "alpaca" },
      },
      {
        kind: "Source",
        label: "IBKR Historical",
        accent: "#10b981",
        defaultParams: { provider: "ibkr" },
      },
      {
        kind: "Source",
        label: "FRED",
        accent: "#10b981",
        defaultParams: { provider: "fred" },
      },
    ],
  },
  {
    title: "Transforms",
    items: [
      {
        kind: "Transform",
        label: "Resample",
        accent: "#3b82f6",
        defaultParams: { interval: "1d" },
      },
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
        description: "Run sink.dbt_build for selected models or tags",
        accent: "#ff694b",
        defaultParams: { select: ["tag:aqp_generated"] },
      },
    ],
  },
  {
    title: "Features",
    items: [
      {
        kind: "Feature",
        label: "SMA",
        accent: "#a855f7",
        defaultParams: { window: 20 },
      },
      {
        kind: "Feature",
        label: "RSI",
        accent: "#a855f7",
        defaultParams: { window: 14 },
      },
      {
        kind: "Feature",
        label: "Returns",
        accent: "#a855f7",
        defaultParams: { window: 1 },
      },
    ],
  },
  {
    title: "Execution",
    items: [
      {
        kind: "Plan",
        label: "Plan manifest",
        accent: "#0ea5e9",
        defaultParams: {},
      },
      {
        kind: "Load",
        label: "Load batch",
        accent: "#6366f1",
        defaultParams: { batch_size: 25 },
      },
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
      { kind: "Parquet", label: "Parquet sink", accent: "#f59e0b", defaultParams: { path: "data/parquet/" } },
      { kind: "Index", label: "Chroma index", accent: "#f59e0b", defaultParams: {} },
    ],
  },
];

export const STRATEGY_PALETTE: PaletteSection[] = [
  {
    title: "Signals",
    items: [
      {
        kind: "Signal",
        label: "SMA crossover",
        accent: "#10b981",
        defaultParams: { kind: "sma_cross", fast: 10, slow: 30 },
      },
      {
        kind: "Signal",
        label: "Mean reversion",
        accent: "#10b981",
        defaultParams: { kind: "mean_reversion", window: 20, z_threshold: 2.0 },
      },
      {
        kind: "Signal",
        label: "Momentum",
        accent: "#10b981",
        defaultParams: { kind: "momentum", lookback: 252 },
      },
    ],
  },
  {
    title: "Factors",
    items: [
      {
        kind: "Factor",
        label: "Quality",
        accent: "#a855f7",
        defaultParams: { factor: "quality" },
      },
      {
        kind: "Factor",
        label: "Value",
        accent: "#a855f7",
        defaultParams: { factor: "value" },
      },
    ],
  },
  {
    title: "Rules / Sizing / Risk",
    items: [
      { kind: "Rule", label: "Long/Short", accent: "#3b82f6", defaultParams: { kind: "long_short" } },
      { kind: "Sizing", label: "Equal weight", accent: "#3b82f6", defaultParams: { kind: "equal_weight" } },
      { kind: "Sizing", label: "Risk parity", accent: "#3b82f6", defaultParams: { kind: "risk_parity" } },
      { kind: "Risk", label: "Stop loss", accent: "#ef4444", defaultParams: { stop_pct: 0.05 } },
      { kind: "Risk", label: "Max DD halt", accent: "#ef4444", defaultParams: { max_dd: 0.15 } },
    ],
  },
  {
    title: "Outputs",
    items: [
      {
        kind: "Portfolio",
        label: "Portfolio assembler",
        accent: "#f59e0b",
        defaultParams: {},
      },
      {
        kind: "Execution",
        label: "Execution",
        accent: "#f59e0b",
        defaultParams: { broker: "alpaca" },
      },
    ],
  },
];
