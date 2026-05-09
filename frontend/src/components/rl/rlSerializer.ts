import type { FlowGraph } from "@/components/flow/types";

import { RL_MODULE_PATHS } from "./rlPalette";

export interface BuildSpec {
  class: string;
  module_path: string;
  kwargs: Record<string, unknown>;
}

export interface RLExperimentSpecPayload {
  name: string;
  slug?: string;
  kind?: string;
  description?: string;
  env: BuildSpec | null;
  observation: { spec: BuildSpec | null } | null;
  action: { spec: BuildSpec | null } | null;
  reward: { spec: BuildSpec | null } | null;
  terminations: { specs: BuildSpec[] };
  data_pipeline: { spec: BuildSpec | null } | null;
  agent: BuildSpec | null;
  ensembler: { spec: BuildSpec | null } | null;
  training?: Record<string, unknown>;
  evaluation?: Record<string, unknown>;
  experiment?: BuildSpec | null;
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
const OBSERVATION_KINDS = new Set([
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
const REWARD_KINDS = new Set(
  Object.keys(RL_MODULE_PATHS).filter((k) => RL_MODULE_PATHS[k]!.startsWith("aqp.rl.rewards") || k === "CompositeReward"),
);
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
const DATA_KINDS = new Set([
  "IcebergRLDataPipeline",
  "YahooFinanceRLDataPipeline",
  "AlpacaRLDataPipeline",
  "LiveStreamingRLDataPipeline",
  "ReplayRLDataPipeline",
]);
const EXPERIMENT_KINDS = new Set([
  "BasicRLExperiment",
  "WalkForwardRLExperiment",
  "RewardAblationExperiment",
  "RLAlphaBacktestExperiment",
]);

function buildSpecFor(node: FlowGraph["nodes"][number]): BuildSpec {
  return {
    class: node.data.kind,
    module_path: RL_MODULE_PATHS[node.data.kind] ?? "",
    kwargs: { ...(node.data.params ?? {}) },
  };
}

function findOne(graph: FlowGraph, kinds: Set<string>): FlowGraph["nodes"][number] | undefined {
  return graph.nodes.find((n) => kinds.has(n.data.kind));
}

/**
 * Build the `RLExperimentSpec` payload from the Lab canvas. Reward
 * terms are aggregated under a single `CompositeReward` (or, if the
 * canvas already has a `CompositeReward` node, its kwargs are used as
 * the wrapper and reward terms are pushed into `kwargs.terms`).
 */
export function serializeRLExperiment(
  graph: FlowGraph,
  meta: { name: string; description?: string },
): RLExperimentSpecPayload {
  const env = findOne(graph, ENV_KINDS);
  const observation = findOne(graph, OBSERVATION_KINDS);
  const action = findOne(graph, ACTION_KINDS);
  const dataPipeline = findOne(graph, DATA_KINDS);
  const agent = findOne(graph, AGENT_KINDS);
  const ensembler = findOne(graph, ENSEMBLER_KINDS);
  const experiment = findOne(graph, EXPERIMENT_KINDS);

  const rewardNodes = graph.nodes.filter((n) => REWARD_KINDS.has(n.data.kind));
  const compositeNode = rewardNodes.find((n) => n.data.kind === "CompositeReward");
  const otherRewards = rewardNodes.filter((n) => n.data.kind !== "CompositeReward");

  let rewardSpec: BuildSpec | null = null;
  if (compositeNode || otherRewards.length > 0) {
    const baseKwargs = compositeNode ? { ...(compositeNode.data.params ?? {}) } : {};
    const terms = otherRewards.map(buildSpecFor);
    rewardSpec = {
      class: "CompositeReward",
      module_path: RL_MODULE_PATHS.CompositeReward!,
      kwargs: { ...baseKwargs, terms },
    };
  }

  const terminations = graph.nodes
    .filter((n) => TERMINATION_KINDS.has(n.data.kind))
    .map(buildSpecFor);

  return {
    name: meta.name,
    ...(meta.description !== undefined ? { description: meta.description } : {}),
    env: env ? buildSpecFor(env) : null,
    observation: observation ? { spec: buildSpecFor(observation) } : null,
    action: action ? { spec: buildSpecFor(action) } : null,
    reward: rewardSpec ? { spec: rewardSpec } : null,
    terminations: { specs: terminations },
    data_pipeline: dataPipeline ? { spec: buildSpecFor(dataPipeline) } : null,
    agent: agent ? buildSpecFor(agent) : null,
    ensembler: ensembler ? { spec: buildSpecFor(ensembler) } : null,
    experiment: experiment ? buildSpecFor(experiment) : null,
  };
}
