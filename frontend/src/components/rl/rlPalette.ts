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
// Phase D — hybrid agentic-RL UI studios.
const BACKBONE_ACCENT = "#14b8a6";    // teal — policy backbones
const ADVANTAGE_ACCENT = "#f43f5e";   // rose — advantage estimators
const PIPELINE_ACCENT = "#84cc16";    // lime — weight-centric pipeline (f_S/f_A/f_T/f_R)

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
  // Phase D — Hybrid agentic-RL UI studios: policy backbones.
  {
    title: "Policy backbones",
    items: [
      tile("TransformerBackbone", "Transformer", BACKBONE_ACCENT, "Self-attention encoder", {
        sequence_length: 30,
        n_heads: 4,
        n_layers: 2,
      }),
      tile("RecurrentBackbone", "Recurrent (LSTM/GRU/RNN)", BACKBONE_ACCENT, "Causal sequence encoder", {
        sequence_length: 30,
        cell: "lstm",
        hidden_size: 128,
        num_layers: 2,
      }),
      tile("AutoencoderBackbone", "Autoencoder", BACKBONE_ACCENT, "MLP bottleneck", {
        sequence_length: 1,
        hidden_dims: [256, 128],
        bottleneck_dim: 64,
      }),
      tile("PatchTSTBackbone", "PatchTST", BACKBONE_ACCENT, "Patch-tokenised Transformer", {
        sequence_length: 32,
        patch_length: 4,
        d_model: 64,
        n_heads: 4,
      }),
    ],
  },
  // Phase D — Hybrid agentic-RL UI studios: advantage estimators.
  {
    title: "Advantage",
    items: [
      tile("ReinforcePlusPlusAdvantage", "REINFORCE++", ADVANTAGE_ACCENT, "NeMo-RL port", {
        minus_baseline: true,
        global_normalization: true,
        leave_one_out: true,
      }),
      tile("GRPOAdvantage", "GRPO", ADVANTAGE_ACCENT, "Group-relative no-critic", {
        normalise_by_cohort_std: true,
      }),
      tile("GAEAdvantage", "GAE", ADVANTAGE_ACCENT, "Critic-based classic", {
        gamma: 0.99,
        lam: 0.95,
        normalise: true,
      }),
    ],
  },
  // Phase D — Hybrid agentic-RL UI studios: weight-centric pipeline
  // (FinRL-X f_S -> f_A -> f_T -> f_R). Picked here for canvas-style
  // composition; the WeightCentricPipelinePanel exposes the same
  // shape inline for the meta panel.
  {
    title: "Portfolio pipeline",
    items: [
      tile("StaticUniverseSelector", "Static universe (f_S)", PIPELINE_ACCENT, "Passthrough", {}),
      tile("LiquiditySelector", "Liquidity filter (f_S)", PIPELINE_ACCENT, "Min ADV", {
        min_dollar_volume: 1_000_000,
      }),
      tile("IdentityAllocator", "Identity allocator (f_A)", PIPELINE_ACCENT, "Raw RL action", {}),
      tile("SoftmaxAllocator", "Softmax allocator (f_A)", PIPELINE_ACCENT, "Long-only simplex", {
        temperature: 1.0,
      }),
      tile("ConstantTimingAdjuster", "Constant timing (f_T)", PIPELINE_ACCENT, "No scaling", {}),
      tile("TurbulenceTimingAdjuster", "Turbulence (f_T)", PIPELINE_ACCENT, "Regime gating", {
        threshold: 140.0,
        cooldown_scale: 0.0,
      }),
      tile("VolatilityTargetingTimingAdjuster", "Vol target (f_T)", PIPELINE_ACCENT, "Annualised", {
        target_vol: 0.1,
        max_scale: 2.0,
      }),
      tile("PositionCapRiskOverlay", "Position cap (f_R)", PIPELINE_ACCENT, "Per-position clamp", {
        max_position_pct: 0.3,
        mark_truncated: true,
      }),
      tile("GrossExposureRiskOverlay", "Gross cap (f_R)", PIPELINE_ACCENT, "Sum-abs scale", {
        max_gross: 1.0,
      }),
      tile("StackedRiskOverlay", "Stacked overlay (f_R)", PIPELINE_ACCENT, "Cap + gross", {}),
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
  // Phase D — policy backbones.
  TransformerBackbone: "aqp.rl.policies.backbones.transformer",
  RecurrentBackbone: "aqp.rl.policies.backbones.recurrent",
  AutoencoderBackbone: "aqp.rl.policies.backbones.autoencoder",
  PatchTSTBackbone: "aqp.rl.policies.backbones.patchtst",
  // Phase D — advantage estimators.
  ReinforcePlusPlusAdvantage: "aqp.rl.advantage.reinforce_plus_plus",
  GRPOAdvantage: "aqp.rl.advantage.grpo",
  GAEAdvantage: "aqp.rl.advantage.gae",
  // Phase D — weight-centric portfolio pipeline (f_S/f_A/f_T/f_R).
  StaticUniverseSelector: "aqp.rl.portfolio.selector",
  LiquiditySelector: "aqp.rl.portfolio.selector",
  IdentityAllocator: "aqp.rl.portfolio.allocator",
  SoftmaxAllocator: "aqp.rl.portfolio.allocator",
  ConstantTimingAdjuster: "aqp.rl.portfolio.timing",
  TurbulenceTimingAdjuster: "aqp.rl.portfolio.timing",
  VolatilityTargetingTimingAdjuster: "aqp.rl.portfolio.timing",
  PositionCapRiskOverlay: "aqp.rl.portfolio.risk_overlay",
  GrossExposureRiskOverlay: "aqp.rl.portfolio.risk_overlay",
  StackedRiskOverlay: "aqp.rl.portfolio.risk_overlay",
};

/** Phase D — kinds that belong to the FinRL-X weight-centric pipeline (`f_S/f_A/f_T/f_R`). */
export const WEIGHT_CENTRIC_KINDS: Record<string, "selector" | "allocator" | "timing" | "risk_overlay"> = {
  StaticUniverseSelector: "selector",
  LiquiditySelector: "selector",
  IdentityAllocator: "allocator",
  SoftmaxAllocator: "allocator",
  ConstantTimingAdjuster: "timing",
  TurbulenceTimingAdjuster: "timing",
  VolatilityTargetingTimingAdjuster: "timing",
  PositionCapRiskOverlay: "risk_overlay",
  GrossExposureRiskOverlay: "risk_overlay",
  StackedRiskOverlay: "risk_overlay",
};

/** Phase D — backbone kinds (`rl_policy_backbone`). */
export const BACKBONE_KINDS: ReadonlySet<string> = new Set([
  "TransformerBackbone",
  "RecurrentBackbone",
  "AutoencoderBackbone",
  "PatchTSTBackbone",
]);

/** Phase D — advantage estimator kinds (`rl_advantage_estimator`). */
export const ADVANTAGE_KINDS: ReadonlySet<string> = new Set([
  "ReinforcePlusPlusAdvantage",
  "GRPOAdvantage",
  "GAEAdvantage",
]);

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
