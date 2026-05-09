import type { PaletteItem, PaletteSection } from "@/components/flow/types";

const DATA_ACCENT = "#0ea5e9";
const ENV_ACCENT = "#22c55e";
const OBS_ACCENT = "#06b6d4";
const ACTION_ACCENT = "#f59e0b";
const REWARD_ACCENT = "#a855f7";
const TERM_ACCENT = "#ef4444";
const AGENT_ACCENT = "#3b82f6";
const ENSEMBLE_ACCENT = "#8b5cf6";
const EXPERIMENT_ACCENT = "#ec4899";

function tile(
  kind: string,
  label: string,
  accent: string,
  description?: string,
  defaultParams: Record<string, unknown> = {},
): PaletteItem {
  return {
    kind,
    label,
    accent,
    ...(description !== undefined ? { description } : {}),
    defaultParams,
  };
}

export const RL_PALETTE: PaletteSection[] = [
  {
    title: "Data pipeline",
    items: [
      tile("IcebergRLDataPipeline", "Iceberg pipeline", DATA_ACCENT, "AQP catalog", {
        indicators: ["macd", "rsi_14"],
        use_turbulence: true,
      }),
      tile("YahooFinanceRLDataPipeline", "Yahoo Finance", DATA_ACCENT, "FinRL DataProcessor"),
      tile("AlpacaRLDataPipeline", "Alpaca", DATA_ACCENT, "Paper-trading source"),
      tile("LiveStreamingRLDataPipeline", "Live streaming", DATA_ACCENT, "Kafka / Flink"),
      tile("ReplayRLDataPipeline", "Replay", DATA_ACCENT, "Offline rl.trajectories"),
    ],
  },
  {
    title: "Environment",
    items: [
      tile("StockTradingEnv", "StockTradingEnv", ENV_ACCENT, "Continuous portfolio"),
      tile("PortfolioAllocationEnv", "PortfolioAllocationEnv", ENV_ACCENT, "Softmax weights"),
      tile("StockTradingDiscreteEnv", "Discrete single-stock", ENV_ACCENT, "Buy / sell / hold"),
      tile("FinRLStockTradingEnv", "FinRL StockTradingEnv", ENV_ACCENT, "Pandas / share-lots"),
      tile("FinRLStockTradingNpEnv", "FinRL StockTradingEnv (NP)", ENV_ACCENT, "Array-backed"),
      tile("FinRLPortfolioCovEnv", "FinRL PortfolioCov", ENV_ACCENT, "Cov + softmax"),
      tile("FinRLCryptoEnv", "FinRL Crypto", ENV_ACCENT, "24/7 crypto"),
      tile("OptionsTradingEnv", "Options trading", ENV_ACCENT, "Greeks-aware"),
      tile("ExecutionEnv", "Execution", ENV_ACCENT, "Order-routing"),
      tile("MarketMakingEnv", "Market making", ENV_ACCENT, "Spread / inventory"),
    ],
  },
  {
    title: "Observation",
    items: [
      tile("PortfolioStateBuilder", "Portfolio state", OBS_ACCENT),
      tile("TechnicalIndicatorBuilder", "Technical indicators", OBS_ACCENT, "stockstats"),
      tile("CovarianceBuilder", "Covariance", OBS_ACCENT, "Rolling Σ"),
      tile("TurbulenceBuilder", "Turbulence", OBS_ACCENT),
      tile("VIXBuilder", "VIX", OBS_ACCENT),
      tile("LookbackStackBuilder", "Lookback stack", OBS_ACCENT),
      tile("FundamentalBuilder", "Fundamental", OBS_ACCENT),
      tile("MicrostructureBuilder", "Microstructure", OBS_ACCENT),
      tile("StackedObservationBuilder", "Stacked composite", OBS_ACCENT, "Compose multiple"),
    ],
  },
  {
    title: "Action",
    items: [
      tile("ContinuousWeightsAction", "Continuous weights", ACTION_ACCENT),
      tile("SoftmaxWeightsAction", "Softmax weights", ACTION_ACCENT),
      tile("IntegerSharesAction", "Integer shares", ACTION_ACCENT),
      tile("DiscreteBuySellHoldAction", "Buy / sell / hold", ACTION_ACCENT),
      tile("MultiDiscreteAction", "Multi-discrete", ACTION_ACCENT),
      tile("TargetPositionAction", "Target position", ACTION_ACCENT),
    ],
  },
  {
    title: "Reward",
    items: [
      tile("PnLTerm", "PnL", REWARD_ACCENT, "weight=1.0", { weight: 1.0 }),
      tile("LogReturnTerm", "Log return", REWARD_ACCENT, "weight=1.0", { weight: 1.0 }),
      tile("SharpeTerm", "Sharpe", REWARD_ACCENT, "weight=0.5", { weight: 0.5 }),
      tile("SortinoTerm", "Sortino", REWARD_ACCENT, "weight=0.5", { weight: 0.5 }),
      tile("DrawdownPenaltyTerm", "Drawdown penalty", REWARD_ACCENT, "weight=0.2", {
        weight: 0.2,
      }),
      tile("VolatilityPenaltyTerm", "Volatility penalty", REWARD_ACCENT, "weight=0.1", {
        weight: 0.1,
      }),
      tile("TurnoverPenaltyTerm", "Turnover penalty", REWARD_ACCENT, "weight=0.05", {
        weight: 0.05,
      }),
      tile("TransactionCostTerm", "Transaction cost", REWARD_ACCENT),
      tile("SlippagePenaltyTerm", "Slippage penalty", REWARD_ACCENT),
      tile("TurbulenceGateTerm", "Turbulence gate", REWARD_ACCENT),
      tile("MarginCallTerm", "Margin call", REWARD_ACCENT),
      tile("BenchmarkOutperformanceTerm", "Benchmark outperformance", REWARD_ACCENT),
      tile("RiskParityTerm", "Risk parity", REWARD_ACCENT),
      tile("PotentialBasedShaping", "Potential-based shaping", REWARD_ACCENT),
      tile("CompositeReward", "Composite", REWARD_ACCENT, "Wraps reward terms"),
    ],
  },
  {
    title: "Termination",
    items: [
      tile("HorizonTermination", "Horizon", TERM_ACCENT),
      tile("DrawdownTermination", "Drawdown", TERM_ACCENT, "max_dd=0.25", { max_dd: 0.25 }),
      tile("MarginCallTermination", "Margin call", TERM_ACCENT),
      tile("TurbulenceTermination", "Turbulence", TERM_ACCENT, "turbulence_threshold=140", {
        turbulence_threshold: 140,
      }),
    ],
  },
  {
    title: "Agent",
    items: [
      tile("SB3Adapter", "SB3 adapter", AGENT_ACCENT, "PPO / SAC / TD3 / DQN", {
        algo: "ppo",
        kwargs: { n_steps: 2048, learning_rate: 3e-4 },
      }),
      tile("ElegantRLAdapter", "ElegantRL", AGENT_ACCENT, "Off-policy fast"),
      tile("RayRLlibAdapter", "RLlib", AGENT_ACCENT, "Distributed"),
      tile("CleanRLAdapter", "CleanRL", AGENT_ACCENT, "Single-file"),
      tile("LLMHybridAgent", "LLM hybrid", AGENT_ACCENT, "FinRobot-style"),
    ],
  },
  {
    title: "Ensembler",
    items: [
      tile("WalkForwardEnsembler", "Walk-forward", ENSEMBLE_ACCENT, "FinRL DRLEnsembleAgent port"),
      tile("BestOfNRunner", "Best-of-N", ENSEMBLE_ACCENT),
      tile("CurriculumRunner", "Curriculum", ENSEMBLE_ACCENT),
      tile("MetaEnsembleRunner", "Meta-ensemble", ENSEMBLE_ACCENT),
    ],
  },
  {
    title: "Experiment",
    items: [
      tile("BasicRLExperiment", "Basic", EXPERIMENT_ACCENT),
      tile("WalkForwardRLExperiment", "Walk-forward", EXPERIMENT_ACCENT),
      tile("RewardAblationExperiment", "Reward ablation", EXPERIMENT_ACCENT),
      tile("RLAlphaBacktestExperiment", "RL + alpha backtest", EXPERIMENT_ACCENT),
    ],
  },
];

/** Map every kind in the palette to its canonical Python module path. */
export const RL_MODULE_PATHS: Record<string, string> = {
  IcebergRLDataPipeline: "aqp.rl.data_pipelines.iceberg",
  YahooFinanceRLDataPipeline: "aqp.rl.data_pipelines.yahoo",
  AlpacaRLDataPipeline: "aqp.rl.data_pipelines.alpaca",
  LiveStreamingRLDataPipeline: "aqp.rl.data_pipelines.streaming",
  ReplayRLDataPipeline: "aqp.rl.data_pipelines.replay",
  StockTradingEnv: "aqp.rl.envs.stock_trading_env",
  PortfolioAllocationEnv: "aqp.rl.envs.portfolio_env",
  StockTradingDiscreteEnv: "aqp.rl.envs.stock_trading_discrete",
  FinRLStockTradingEnv: "aqp.rl.envs.finrl_stock_env",
  FinRLStockTradingNpEnv: "aqp.rl.envs.finrl_stock_np_env",
  FinRLPortfolioCovEnv: "aqp.rl.envs.finrl_portfolio_cov_env",
  FinRLCryptoEnv: "aqp.rl.envs.finrl_crypto_env",
  OptionsTradingEnv: "aqp.rl.envs.options_env",
  ExecutionEnv: "aqp.rl.envs.execution_env",
  MarketMakingEnv: "aqp.rl.envs.market_making_env",
  PortfolioStateBuilder: "aqp.rl.observations.portfolio_state",
  TechnicalIndicatorBuilder: "aqp.rl.observations.technical",
  CovarianceBuilder: "aqp.rl.observations.covariance",
  TurbulenceBuilder: "aqp.rl.observations.turbulence",
  VIXBuilder: "aqp.rl.observations.vix",
  LookbackStackBuilder: "aqp.rl.observations.lookback",
  FundamentalBuilder: "aqp.rl.observations.fundamental",
  MicrostructureBuilder: "aqp.rl.observations.microstructure",
  StackedObservationBuilder: "aqp.rl.core.observation",
  ContinuousWeightsAction: "aqp.rl.core.action",
  SoftmaxWeightsAction: "aqp.rl.core.action",
  IntegerSharesAction: "aqp.rl.core.action",
  DiscreteBuySellHoldAction: "aqp.rl.core.action",
  MultiDiscreteAction: "aqp.rl.core.action",
  TargetPositionAction: "aqp.rl.core.action",
  PnLTerm: "aqp.rl.rewards.pnl",
  LogReturnTerm: "aqp.rl.rewards.pnl",
  SharpeTerm: "aqp.rl.rewards.risk",
  SortinoTerm: "aqp.rl.rewards.risk",
  DrawdownPenaltyTerm: "aqp.rl.rewards.risk",
  VolatilityPenaltyTerm: "aqp.rl.rewards.risk",
  TurnoverPenaltyTerm: "aqp.rl.rewards.cost",
  TransactionCostTerm: "aqp.rl.rewards.cost",
  SlippagePenaltyTerm: "aqp.rl.rewards.cost",
  TurbulenceGateTerm: "aqp.rl.rewards.gating",
  MarginCallTerm: "aqp.rl.rewards.gating",
  BenchmarkOutperformanceTerm: "aqp.rl.rewards.constraint",
  RiskParityTerm: "aqp.rl.rewards.constraint",
  PotentialBasedShaping: "aqp.rl.rewards.shaping",
  CompositeReward: "aqp.rl.core.reward",
  HorizonTermination: "aqp.rl.terminations.horizon",
  DrawdownTermination: "aqp.rl.terminations.drawdown",
  MarginCallTermination: "aqp.rl.terminations.margin_call",
  TurbulenceTermination: "aqp.rl.terminations.turbulence",
  SB3Adapter: "aqp.rl.agents.sb3_adapter",
  ElegantRLAdapter: "aqp.rl.agents.elegantrl_adapter",
  RayRLlibAdapter: "aqp.rl.agents.rllib_adapter",
  CleanRLAdapter: "aqp.rl.agents.cleanrl_adapter",
  LLMHybridAgent: "aqp.rl.agents.llm_hybrid",
  WalkForwardEnsembler: "aqp.rl.ensemblers.walk_forward",
  BestOfNRunner: "aqp.rl.ensemblers.best_of_n",
  CurriculumRunner: "aqp.rl.ensemblers.curriculum",
  MetaEnsembleRunner: "aqp.rl.ensemblers.meta_ensemble",
  BasicRLExperiment: "aqp.rl.experiments.basic",
  WalkForwardRLExperiment: "aqp.rl.experiments.walk_forward",
  RewardAblationExperiment: "aqp.rl.experiments.ablation",
  RLAlphaBacktestExperiment: "aqp.rl.experiments.alpha_backtest",
};

/**
 * Per-kind accent table consumed by AqpNodeCard via WorkflowEditor's
 * `accentByKind` prop.
 */
export const RL_NODE_ACCENTS: Record<string, string> = {};
for (const section of RL_PALETTE) {
  for (const item of section.items) {
    if (item.accent) RL_NODE_ACCENTS[item.kind] = item.accent;
  }
}
