import type { PaletteSection } from "@/components/flow/types";

/**
 * RL palette definitions for the WorkflowEditor.
 *
 * Sections mirror the kinds returned by ``GET /rl/components``:
 * env / observation / action / reward / termination / agent / data /
 * ensembler / experiment / trajectory_store. Each section's items
 * correspond to registered AQP RL components (``rl_kind``).
 */

export const RL_DATA_PIPELINE_SECTION: PaletteSection = {
  title: "Data pipeline",
  items: [
    {
      kind: "IcebergRLDataPipeline",
      label: "Iceberg pipeline",
      description: "AQP catalog (default)",
      group: "data",
      accent: "#0ea5e9",
      defaultParams: { indicators: ["macd", "rsi_14"], use_turbulence: true },
    },
    {
      kind: "YahooFinanceRLDataPipeline",
      label: "Yahoo Finance",
      description: "FinRL DataProcessor parity",
      group: "data",
      accent: "#0ea5e9",
    },
    {
      kind: "AlpacaRLDataPipeline",
      label: "Alpaca",
      description: "FinRL paper-trading source",
      group: "data",
      accent: "#0ea5e9",
    },
    {
      kind: "LiveStreamingRLDataPipeline",
      label: "Live streaming",
      description: "Kafka / Flink",
      group: "data",
      accent: "#0ea5e9",
    },
    {
      kind: "ReplayRLDataPipeline",
      label: "Replay",
      description: "Offline RL from rl.trajectories",
      group: "data",
      accent: "#0ea5e9",
    },
  ],
};

export const RL_ENV_SECTION: PaletteSection = {
  title: "Environment",
  items: [
    {
      kind: "StockTradingEnv",
      label: "StockTradingEnv",
      description: "Continuous portfolio",
      group: "env",
      accent: "#22c55e",
    },
    {
      kind: "PortfolioAllocationEnv",
      label: "PortfolioAllocationEnv",
      description: "Softmax weights",
      group: "env",
      accent: "#22c55e",
    },
    {
      kind: "StockTradingDiscreteEnv",
      label: "Discrete single-stock",
      description: "Buy / sell / hold",
      group: "env",
      accent: "#22c55e",
    },
    {
      kind: "FinRLStockTradingEnv",
      label: "FinRL StockTradingEnv",
      description: "Pandas / share-lots",
      group: "env",
      accent: "#22c55e",
    },
    {
      kind: "FinRLStockTradingNpEnv",
      label: "FinRL StockTradingEnv (NP)",
      description: "Array-backed fast",
      group: "env",
      accent: "#22c55e",
    },
    {
      kind: "FinRLPortfolioCovEnv",
      label: "FinRL PortfolioCov",
      description: "Cov + softmax",
      group: "env",
      accent: "#22c55e",
    },
    {
      kind: "FinRLCryptoEnv",
      label: "FinRL Crypto",
      description: "Lookback stack",
      group: "env",
      accent: "#22c55e",
    },
    {
      kind: "OptionsTradingEnv",
      label: "Options (preview)",
      description: "Placeholder",
      group: "env",
      accent: "#94a3b8",
    },
    {
      kind: "ExecutionEnv",
      label: "Execution (preview)",
      description: "Placeholder",
      group: "env",
      accent: "#94a3b8",
    },
    {
      kind: "MarketMakingEnv",
      label: "Market making (preview)",
      description: "Placeholder",
      group: "env",
      accent: "#94a3b8",
    },
  ],
};

export const RL_OBSERVATION_SECTION: PaletteSection = {
  title: "Observation builders",
  items: [
    {
      kind: "PortfolioStateBuilder",
      label: "Portfolio state",
      description: "Cash + weights",
      group: "obs",
      accent: "#a855f7",
    },
    {
      kind: "TechnicalIndicatorBuilder",
      label: "Technical indicators",
      description: "FinRL stockstats",
      group: "obs",
      accent: "#a855f7",
    },
    {
      kind: "CovarianceBuilder",
      label: "Covariance matrix",
      description: "FinRL portfolio env",
      group: "obs",
      accent: "#a855f7",
    },
    {
      kind: "TurbulenceBuilder",
      label: "Turbulence",
      description: "Mahalanobis stress",
      group: "obs",
      accent: "#a855f7",
    },
    {
      kind: "VIXBuilder",
      label: "VIX",
      description: "Volatility index merge",
      group: "obs",
      accent: "#a855f7",
    },
    {
      kind: "LookbackStackBuilder",
      label: "Lookback stack",
      description: "FinRL crypto env",
      group: "obs",
      accent: "#a855f7",
    },
    {
      kind: "FundamentalBuilder",
      label: "Fundamentals",
      description: "FinRobot bridge",
      group: "obs",
      accent: "#a855f7",
    },
    {
      kind: "MicrostructureBuilder",
      label: "Microstructure",
      description: "Spread / OFI",
      group: "obs",
      accent: "#a855f7",
    },
    {
      kind: "StackedObservationBuilder",
      label: "Stack composer",
      description: "Concatenate builders",
      group: "obs",
      accent: "#a855f7",
    },
  ],
};

export const RL_ACTION_SECTION: PaletteSection = {
  title: "Action spaces",
  items: [
    {
      kind: "ContinuousWeightsAction",
      label: "Continuous weights",
      description: "PPO / SAC / TD3",
      group: "action",
      accent: "#f59e0b",
    },
    {
      kind: "SoftmaxWeightsAction",
      label: "Softmax weights",
      description: "FinRL StockPortfolio",
      group: "action",
      accent: "#f59e0b",
    },
    {
      kind: "IntegerSharesAction",
      label: "Integer shares",
      description: "FinRL hmax-style",
      group: "action",
      accent: "#f59e0b",
    },
    {
      kind: "DiscreteBuySellHoldAction",
      label: "Discrete BSH",
      description: "FinRL NeurIPS '18",
      group: "action",
      accent: "#f59e0b",
    },
    {
      kind: "MultiDiscreteAction",
      label: "Multi-discrete",
      description: "Per-asset discrete",
      group: "action",
      accent: "#f59e0b",
    },
    {
      kind: "TargetPositionAction",
      label: "Target positions",
      description: "Long / short signed",
      group: "action",
      accent: "#f59e0b",
    },
  ],
};

export const RL_REWARD_SECTION: PaletteSection = {
  title: "Reward terms",
  items: [
    {
      kind: "PnLTerm",
      label: "PnL",
      description: "Δportfolio_value",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "LogReturnTerm",
      label: "Log return",
      description: "Scale-free",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "SharpeTerm",
      label: "Sharpe",
      description: "Rolling annualised",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "SortinoTerm",
      label: "Sortino",
      description: "Downside Sharpe",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "DrawdownPenaltyTerm",
      label: "Drawdown penalty",
      description: "FinRL default",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "VolatilityPenaltyTerm",
      label: "Volatility penalty",
      description: "Realised vol",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "TurnoverPenaltyTerm",
      label: "Turnover penalty",
      description: "FinRL cost block",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "TransactionCostTerm",
      label: "Transaction cost",
      description: "Direct fee",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "SlippagePenaltyTerm",
      label: "Slippage",
      description: "bps × notional",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "TurbulenceGateTerm",
      label: "Turbulence gate",
      description: "FinRL flatten",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "MarginCallTerm",
      label: "Margin call",
      description: "Hard penalty",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "CashIdlePenaltyTerm",
      label: "Cash idle",
      description: "FinRL CashPenaltyEnv",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "BenchmarkOutperformanceTerm",
      label: "Benchmark outperf.",
      description: "vs index",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "RiskParityTerm",
      label: "Risk parity",
      description: "Diversification entropy",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "PotentialBasedShaping",
      label: "Potential shaping",
      description: "γ·Φ(s') - Φ(s)",
      group: "reward",
      accent: "#ef4444",
    },
    {
      kind: "CompositeReward",
      label: "Composite",
      description: "Weighted sum",
      group: "reward",
      accent: "#ef4444",
    },
  ],
};

export const RL_TERMINATION_SECTION: PaletteSection = {
  title: "Terminations",
  items: [
    {
      kind: "HorizonTermination",
      label: "Horizon",
      description: "End of data window",
      group: "termination",
      accent: "#94a3b8",
    },
    {
      kind: "DrawdownTermination",
      label: "Drawdown",
      description: "Underwater stop",
      group: "termination",
      accent: "#94a3b8",
    },
    {
      kind: "MarginCallTermination",
      label: "Margin call",
      description: "Floor breach",
      group: "termination",
      accent: "#94a3b8",
    },
    {
      kind: "TurbulenceTermination",
      label: "Turbulence",
      description: "Stress stop",
      group: "termination",
      accent: "#94a3b8",
    },
  ],
};

export const RL_AGENT_SECTION: PaletteSection = {
  title: "Agents",
  items: [
    {
      kind: "SB3Adapter",
      label: "SB3 adapter",
      description: "PPO / SAC / DDPG / TD3 / DQN",
      group: "agent",
      accent: "#3b82f6",
      defaultParams: { algorithm: "PPO" },
    },
    {
      kind: "ElegantRLAdapter",
      label: "ElegantRL",
      description: "FinRL parity backend",
      group: "agent",
      accent: "#3b82f6",
    },
    {
      kind: "RayRLlibAdapter",
      label: "Ray RLlib",
      description: "Distributed",
      group: "agent",
      accent: "#3b82f6",
    },
    {
      kind: "CleanRLAdapter",
      label: "CleanRL PPO",
      description: "Single-file reference",
      group: "agent",
      accent: "#3b82f6",
    },
    {
      kind: "LLMHybridAgent",
      label: "LLM hybrid",
      description: "FinRobot blend",
      group: "agent",
      accent: "#3b82f6",
    },
  ],
};

export const RL_ENSEMBLER_SECTION: PaletteSection = {
  title: "Ensemblers",
  items: [
    {
      kind: "WalkForwardEnsembler",
      label: "Walk-forward",
      description: "FinRL ensemble (Sharpe pick)",
      group: "ensembler",
      accent: "#14b8a6",
    },
    {
      kind: "BestOfNRunner",
      label: "Best-of-N",
      description: "Hyperparam search",
      group: "ensembler",
      accent: "#14b8a6",
    },
    {
      kind: "CurriculumRunner",
      label: "Curriculum",
      description: "Progressive windows",
      group: "ensembler",
      accent: "#14b8a6",
    },
    {
      kind: "MetaEnsembleRunner",
      label: "Meta-ensemble",
      description: "Action blend",
      group: "ensembler",
      accent: "#14b8a6",
    },
  ],
};

export const RL_EXPERIMENT_SECTION: PaletteSection = {
  title: "Experiments",
  items: [
    {
      kind: "BasicRLExperiment",
      label: "Basic experiment",
      description: "Train + holdout eval",
      group: "experiment",
      accent: "#7c3aed",
    },
    {
      kind: "WalkForwardRLExperiment",
      label: "Walk-forward",
      description: "Rolling train→eval",
      group: "experiment",
      accent: "#7c3aed",
    },
    {
      kind: "RewardAblationExperiment",
      label: "Reward ablation",
      description: "Term sweep",
      group: "experiment",
      accent: "#7c3aed",
    },
    {
      kind: "RLAlphaBacktestExperiment",
      label: "RL → backtest",
      description: "Policy as alpha",
      group: "experiment",
      accent: "#7c3aed",
    },
  ],
};

export const RL_PALETTE: PaletteSection[] = [
  RL_DATA_PIPELINE_SECTION,
  RL_ENV_SECTION,
  RL_OBSERVATION_SECTION,
  RL_ACTION_SECTION,
  RL_REWARD_SECTION,
  RL_TERMINATION_SECTION,
  RL_AGENT_SECTION,
  RL_ENSEMBLER_SECTION,
  RL_EXPERIMENT_SECTION,
];

export const RL_REWARD_PALETTE: PaletteSection[] = [RL_REWARD_SECTION];
export const RL_OBSERVATION_PALETTE: PaletteSection[] = [RL_OBSERVATION_SECTION];
export const RL_ENV_PALETTE: PaletteSection[] = [
  RL_DATA_PIPELINE_SECTION,
  RL_ENV_SECTION,
  RL_OBSERVATION_SECTION,
  RL_ACTION_SECTION,
  RL_REWARD_SECTION,
  RL_TERMINATION_SECTION,
];
export const RL_AGENT_PALETTE: PaletteSection[] = [RL_AGENT_SECTION];
export const RL_EXPERIMENT_PALETTE: PaletteSection[] = [RL_EXPERIMENT_SECTION, RL_ENSEMBLER_SECTION];
