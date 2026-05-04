import type { PaletteSection } from "@/components/flow/types";

/**
 * Drag tiles for the Bot Builder canvas. Each tile drops a node whose
 * ``data.kind`` and ``data.params`` round-trip through
 * :func:`serializeBotSpec` to a server-side ``BotSpec`` payload.
 *
 * Eight buckets:
 * - **Universe** – ``data.kind="Universe"``. Symbols + optional model.
 * - **Data**     – ingestion preset / source.
 * - **Strategy** – the alpha/portfolio/risk/execution graph.
 * - **Engine**   – backtest engine shortcut + kwargs.
 * - **ML**       – ``ModelDeployment`` references.
 * - **Agent**    – ``AgentSpec`` reference (research / supervisor / per-bar).
 * - **RAG**      – HierarchicalRAG retrieval clause.
 * - **Metric**   – evaluation metric.
 * - **Risk**     – risk caps.
 * - **Deploy**   – deployment target (paper / k8s / backtest_only).
 */
export const BOT_PALETTE: PaletteSection[] = [
  {
    title: "Universe",
    items: [
      {
        kind: "Universe",
        label: "Static symbols",
        accent: "#06b6d4",
        defaultParams: { symbols: ["AAPL.NASDAQ", "MSFT.NASDAQ"] },
      },
      {
        kind: "Universe",
        label: "Universe model",
        description: "Registry-driven IUniverseSelectionModel",
        accent: "#06b6d4",
        defaultParams: { class: "StaticUniverse", module_path: "aqp.strategies.universes", kwargs: {} },
      },
    ],
  },
  {
    title: "Data",
    items: [
      {
        kind: "DataPipeline",
        label: "OHLCV daily",
        description: "preset=ohlcv-daily",
        accent: "#14b8a6",
        defaultParams: { preset: "ohlcv-daily", source: "alpaca" },
      },
      {
        kind: "DataPipeline",
        label: "Custom source",
        accent: "#14b8a6",
        defaultParams: { preset: "", source: "" },
      },
    ],
  },
  {
    title: "Strategy",
    items: [
      {
        kind: "Strategy",
        label: "FrameworkAlgorithm",
        description: "universe -> alpha -> portfolio -> risk -> exec",
        accent: "#10b981",
        defaultParams: {
          class: "FrameworkAlgorithm",
          module_path: "aqp.strategies.framework",
          kwargs: {
            alpha_model: { class: "DualMACrossoverAlpha", kwargs: { fast: 10, slow: 50 } },
            portfolio_model: { class: "EqualWeightPortfolio" },
            risk_model: { class: "NoOpRiskModel" },
            execution_model: { class: "ImmediateExecutionModel" },
          },
        },
      },
    ],
  },
  {
    title: "Engine",
    items: [
      {
        kind: "Engine",
        label: "vbt-pro signals",
        accent: "#f59e0b",
        defaultParams: { engine: "vbt-pro:signals", kwargs: { initial_cash: 100000.0 } },
      },
      {
        kind: "Engine",
        label: "vbt-pro orders",
        accent: "#f59e0b",
        defaultParams: { engine: "vbt-pro:orders", kwargs: {} },
      },
      {
        kind: "Engine",
        label: "Event-driven",
        description: "True per-bar Python (agents)",
        accent: "#f59e0b",
        defaultParams: { engine: "event", kwargs: {} },
      },
    ],
  },
  {
    title: "ML model",
    items: [
      {
        kind: "MLModel",
        label: "Deployment ref",
        description: "ModelDeployment id from /ml/deployments",
        accent: "#a855f7",
        defaultParams: { deployment_id: "", role: "alpha", weight: 1.0 },
      },
    ],
  },
  {
    title: "Agents",
    items: [
      {
        kind: "Agent",
        label: "Research agent",
        accent: "#3b82f6",
        defaultParams: { spec_name: "research.equity", role: "advisor" },
      },
      {
        kind: "Agent",
        label: "Quant agent (vbt-pro)",
        accent: "#3b82f6",
        defaultParams: { spec_name: "research.quant_vbtpro", role: "supervisor" },
      },
      {
        kind: "Agent",
        label: "Custom agent",
        accent: "#3b82f6",
        defaultParams: { spec_name: "", role: "advisor" },
      },
    ],
  },
  {
    title: "RAG",
    items: [
      {
        kind: "RAG",
        label: "Strategies corpus (L3)",
        accent: "#8b5cf6",
        defaultParams: { levels: ["l3"], orders: ["third"], corpora: ["strategies"], per_level_k: 4, final_k: 8 },
      },
      {
        kind: "RAG",
        label: "SEC filings (L1+L2)",
        accent: "#8b5cf6",
        defaultParams: { levels: ["l1", "l2"], orders: ["second"], corpora: ["sec_filings"], per_level_k: 5, final_k: 12 },
      },
    ],
  },
  {
    title: "Metrics",
    items: [
      {
        kind: "Metric",
        label: "Sharpe",
        accent: "#22c55e",
        defaultParams: { name: "sharpe", threshold: 1.0, direction: "max" },
      },
      {
        kind: "Metric",
        label: "Max drawdown",
        accent: "#22c55e",
        defaultParams: { name: "max_drawdown", threshold: 0.25, direction: "min" },
      },
      {
        kind: "Metric",
        label: "Total return",
        accent: "#22c55e",
        defaultParams: { name: "total_return", direction: "max" },
      },
    ],
  },
  {
    title: "Risk + Deploy",
    items: [
      {
        kind: "Risk",
        label: "Risk caps",
        accent: "#ef4444",
        defaultParams: {
          max_position_pct: 0.25,
          max_daily_loss_pct: 0.02,
          max_drawdown_pct: 0.2,
        },
      },
      {
        kind: "Deploy",
        label: "Paper session",
        accent: "#0ea5e9",
        defaultParams: {
          target: "paper_session",
          brokerage: "simulated",
          feed: "deterministic_replay",
          initial_cash: 100000.0,
          dry_run: true,
        },
      },
      {
        kind: "Deploy",
        label: "Kubernetes",
        accent: "#0ea5e9",
        defaultParams: { target: "kubernetes", namespace: "aqp-bots" },
      },
      {
        kind: "Deploy",
        label: "Backtest only",
        accent: "#0ea5e9",
        defaultParams: { target: "backtest_only" },
      },
    ],
  },
];

export const BOT_NODE_ACCENTS: Record<string, string> = {
  Universe: "#06b6d4",
  DataPipeline: "#14b8a6",
  Strategy: "#10b981",
  Engine: "#f59e0b",
  MLModel: "#a855f7",
  Agent: "#3b82f6",
  RAG: "#8b5cf6",
  Metric: "#22c55e",
  Risk: "#ef4444",
  Deploy: "#0ea5e9",
};
