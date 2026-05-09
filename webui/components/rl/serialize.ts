import type { FlowGraph } from "@/components/flow/types";

/**
 * Maps from a node kind to its canonical Python module path so the
 * server-side ``build_from_config`` can resolve it without relying on
 * the global registry alias (which is preferred but not always set).
 */
const RL_MODULE_PATHS: Record<string, string> = {
  // data
  IcebergRLDataPipeline: "aqp.rl.data_pipelines.iceberg",
  YahooFinanceRLDataPipeline: "aqp.rl.data_pipelines.yahoo",
  AlpacaRLDataPipeline: "aqp.rl.data_pipelines.alpaca",
  LiveStreamingRLDataPipeline: "aqp.rl.data_pipelines.streaming",
  ReplayRLDataPipeline: "aqp.rl.data_pipelines.replay",
  // envs
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
  // observations
  PortfolioStateBuilder: "aqp.rl.observations.portfolio_state",
  TechnicalIndicatorBuilder: "aqp.rl.observations.technical",
  CovarianceBuilder: "aqp.rl.observations.covariance",
  TurbulenceBuilder: "aqp.rl.observations.turbulence",
  VIXBuilder: "aqp.rl.observations.vix",
  LookbackStackBuilder: "aqp.rl.observations.lookback",
  FundamentalBuilder: "aqp.rl.observations.fundamental",
  MicrostructureBuilder: "aqp.rl.observations.microstructure",
  StackedObservationBuilder: "aqp.rl.core.observation",
  // actions
  ContinuousWeightsAction: "aqp.rl.core.action",
  SoftmaxWeightsAction: "aqp.rl.core.action",
  IntegerSharesAction: "aqp.rl.core.action",
  DiscreteBuySellHoldAction: "aqp.rl.core.action",
  MultiDiscreteAction: "aqp.rl.core.action",
  TargetPositionAction: "aqp.rl.core.action",
  // rewards
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
  CashIdlePenaltyTerm: "aqp.rl.rewards.constraint",
  BenchmarkOutperformanceTerm: "aqp.rl.rewards.constraint",
  RiskParityTerm: "aqp.rl.rewards.constraint",
  PotentialBasedShaping: "aqp.rl.rewards.shaping",
  CompositeReward: "aqp.rl.core.reward",
  // terminations
  HorizonTermination: "aqp.rl.terminations.horizon",
  DrawdownTermination: "aqp.rl.terminations.drawdown",
  MarginCallTermination: "aqp.rl.terminations.margin_call",
  TurbulenceTermination: "aqp.rl.terminations.turbulence",
  // agents
  SB3Adapter: "aqp.rl.agents.sb3_adapter",
  ElegantRLAdapter: "aqp.rl.agents.elegantrl_adapter",
  RayRLlibAdapter: "aqp.rl.agents.rllib_adapter",
  CleanRLAdapter: "aqp.rl.agents.cleanrl_adapter",
  LLMHybridAgent: "aqp.rl.agents.llm_hybrid",
  // ensemblers
  WalkForwardEnsembler: "aqp.rl.ensemblers.walk_forward",
  BestOfNRunner: "aqp.rl.ensemblers.best_of_n",
  CurriculumRunner: "aqp.rl.ensemblers.curriculum",
  MetaEnsembleRunner: "aqp.rl.ensemblers.meta_ensemble",
  // experiments
  BasicRLExperiment: "aqp.rl.experiments.basic",
  WalkForwardRLExperiment: "aqp.rl.experiments.walk_forward",
  RewardAblationExperiment: "aqp.rl.experiments.ablation",
  RLAlphaBacktestExperiment: "aqp.rl.experiments.alpha_backtest",
};

export interface RLEnvSpecPayload {
  env?: BuildSpec | null;
  reward?: { spec?: BuildSpec | null } | null;
  observation?: { spec?: BuildSpec | null } | null;
  action?: { spec?: BuildSpec | null } | null;
  terminations?: { specs: BuildSpec[] };
  data_pipeline?: { spec?: BuildSpec | null } | null;
}

export interface RLExperimentSpecPayload extends RLEnvSpecPayload {
  name: string;
  slug?: string;
  kind?: string;
  description?: string;
  agent?: BuildSpec | null;
  training?: Record<string, unknown>;
  evaluation?: Record<string, unknown>;
  ensembler?: { spec?: BuildSpec | null; members?: BuildSpec[] } | null;
  trajectory_store?: { spec?: BuildSpec | null; enabled?: boolean };
  mlflow?: Record<string, unknown>;
  universe?: { symbols: string[] };
}

export interface BuildSpec {
  class: string;
  module_path?: string;
  kwargs?: Record<string, unknown>;
}

function nodeToBuildSpec(node: FlowGraph["nodes"][number]): BuildSpec {
  const kind = node.data.kind;
  return {
    class: kind,
    module_path: RL_MODULE_PATHS[kind],
    kwargs: { ...(node.data.params ?? {}) },
  };
}

/**
 * Convert a flow graph (from the WorkflowEditor canvas) into an
 * RLExperimentSpec payload by bucketising nodes via their palette
 * group. Reward terms are bundled into a CompositeReward; observation
 * builders into a StackedObservationBuilder; terminations into a list.
 */
export function serializeRLExperimentSpec(graph: FlowGraph, name: string): RLExperimentSpecPayload {
  const envNode = graph.nodes.find((n) => isEnvKind(n.data.kind));
  const dataNode = graph.nodes.find((n) => isDataKind(n.data.kind));
  const observationNodes = graph.nodes.filter((n) => isObservationKind(n.data.kind));
  const actionNode = graph.nodes.find((n) => isActionKind(n.data.kind));
  const rewardTerms = graph.nodes.filter((n) => isRewardTermKind(n.data.kind));
  const terminationNodes = graph.nodes.filter((n) => isTerminationKind(n.data.kind));
  const agentNode = graph.nodes.find((n) => isAgentKind(n.data.kind));
  const ensemblerNode = graph.nodes.find((n) => isEnsemblerKind(n.data.kind));
  const singleObservationNode = observationNodes[0];

  const observationSpec: BuildSpec | null =
    observationNodes.length === 0
      ? null
      : observationNodes.length === 1 && singleObservationNode
        ? nodeToBuildSpec(singleObservationNode)
        : {
            class: "StackedObservationBuilder",
            module_path: RL_MODULE_PATHS.StackedObservationBuilder,
            kwargs: {
              builders: observationNodes.map(nodeToBuildSpec),
            },
          };

  const rewardSpec: BuildSpec | null =
    rewardTerms.length === 0
      ? null
      : {
          class: "CompositeReward",
          module_path: RL_MODULE_PATHS.CompositeReward,
          kwargs: {
            terms: rewardTerms.map(nodeToBuildSpec),
          },
        };

  return {
    name,
    slug: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""),
    kind: "training",
    description: "",
    universe: { symbols: [] },
    data_pipeline: dataNode ? { spec: nodeToBuildSpec(dataNode) } : null,
    env: envNode ? nodeToBuildSpec(envNode) : null,
    observation: observationSpec ? { spec: observationSpec } : null,
    action: actionNode ? { spec: nodeToBuildSpec(actionNode) } : null,
    reward: rewardSpec ? { spec: rewardSpec } : null,
    terminations: { specs: terminationNodes.map(nodeToBuildSpec) },
    agent: agentNode ? nodeToBuildSpec(agentNode) : null,
    training: {},
    evaluation: {},
    ensembler: ensemblerNode ? { spec: nodeToBuildSpec(ensemblerNode) } : null,
    trajectory_store: { enabled: true },
    mlflow: {},
  };
}

const ENV_KINDS = new Set([
  "StockTradingEnv",
  "PortfolioAllocationEnv",
  "StockTradingDiscreteEnv",
  "FinRLStockTradingEnv",
  "FinRLStockTradingNpEnv",
  "FinRLPortfolioCovEnv",
  "FinRLCryptoEnv",
  "OptionsTradingEnv",
  "ExecutionEnv",
  "MarketMakingEnv",
]);

const DATA_KINDS = new Set([
  "IcebergRLDataPipeline",
  "YahooFinanceRLDataPipeline",
  "AlpacaRLDataPipeline",
  "LiveStreamingRLDataPipeline",
  "ReplayRLDataPipeline",
]);

const OBS_KINDS = new Set([
  "PortfolioStateBuilder",
  "TechnicalIndicatorBuilder",
  "CovarianceBuilder",
  "TurbulenceBuilder",
  "VIXBuilder",
  "LookbackStackBuilder",
  "FundamentalBuilder",
  "MicrostructureBuilder",
  "StackedObservationBuilder",
]);

const ACTION_KINDS = new Set([
  "ContinuousWeightsAction",
  "SoftmaxWeightsAction",
  "IntegerSharesAction",
  "DiscreteBuySellHoldAction",
  "MultiDiscreteAction",
  "TargetPositionAction",
]);

const REWARD_KINDS = new Set([
  "PnLTerm",
  "LogReturnTerm",
  "SharpeTerm",
  "SortinoTerm",
  "DrawdownPenaltyTerm",
  "VolatilityPenaltyTerm",
  "TurnoverPenaltyTerm",
  "TransactionCostTerm",
  "SlippagePenaltyTerm",
  "TurbulenceGateTerm",
  "MarginCallTerm",
  "CashIdlePenaltyTerm",
  "BenchmarkOutperformanceTerm",
  "RiskParityTerm",
  "PotentialBasedShaping",
]);

const TERMINATION_KINDS = new Set([
  "HorizonTermination",
  "DrawdownTermination",
  "MarginCallTermination",
  "TurbulenceTermination",
]);

const AGENT_KINDS = new Set([
  "SB3Adapter",
  "ElegantRLAdapter",
  "RayRLlibAdapter",
  "CleanRLAdapter",
  "LLMHybridAgent",
]);

const ENSEMBLER_KINDS = new Set([
  "WalkForwardEnsembler",
  "BestOfNRunner",
  "CurriculumRunner",
  "MetaEnsembleRunner",
]);

export function isEnvKind(kind: string): boolean {
  return ENV_KINDS.has(kind);
}
export function isDataKind(kind: string): boolean {
  return DATA_KINDS.has(kind);
}
export function isObservationKind(kind: string): boolean {
  return OBS_KINDS.has(kind);
}
export function isActionKind(kind: string): boolean {
  return ACTION_KINDS.has(kind);
}
export function isRewardTermKind(kind: string): boolean {
  return REWARD_KINDS.has(kind);
}
export function isTerminationKind(kind: string): boolean {
  return TERMINATION_KINDS.has(kind);
}
export function isAgentKind(kind: string): boolean {
  return AGENT_KINDS.has(kind);
}
export function isEnsemblerKind(kind: string): boolean {
  return ENSEMBLER_KINDS.has(kind);
}

export { RL_MODULE_PATHS };
