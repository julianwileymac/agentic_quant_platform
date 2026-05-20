import type { PaletteSection } from "@/components/flow/types";

/**
 * Strategy Composer palette. Builds a spec like
 * `{universe, alpha[], factor[], rule[], sizing[], risk[], portfolio, execution}`.
 */
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
      { kind: "Factor", label: "Quality", accent: "#a855f7", defaultParams: { factor: "quality" } },
      { kind: "Factor", label: "Value", accent: "#a855f7", defaultParams: { factor: "value" } },
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
      { kind: "Portfolio", label: "Portfolio assembler", accent: "#f59e0b", defaultParams: {} },
      { kind: "Execution", label: "Execution", accent: "#f59e0b", defaultParams: { broker: "alpaca" } },
    ],
  },
];

export const STRATEGY_NODE_ACCENTS: Record<string, string> = {
  Signal: "#10b981",
  Factor: "#a855f7",
  Rule: "#3b82f6",
  Sizing: "#3b82f6",
  Risk: "#ef4444",
  Portfolio: "#f59e0b",
  Execution: "#f59e0b",
};
