import type { FlowGraph } from "@/components/flow/types";

import { ADVANTAGE_KINDS, BACKBONE_KINDS, RL_MODULE_PATHS, WEIGHT_CENTRIC_KINDS } from "./rlPalette";

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

/**
 * Phase D meta-panel fields surfaced by the RL Lab as inline pickers
 * (instead of canvas tiles). The serializer threads them onto the
 * canonical RLExperimentSpec shape.
 */
export interface RLExperimentMeta {
  name: string;
  description?: string;
  /** Advantage estimator selected via the meta-panel picker. */
  advantage?: BuildSpec | null;
  /** Stop-properly penalty coefficient (`null` disables the wrapper). */
  stop_properly_penalty_coef?: number | null;
  /**
   * Pre-built `policy_kwargs` block emitted by the BackbonePicker —
   * merged into `agent.kwargs.policy_kwargs` when the agent is SB3.
   */
  policy_kwargs?: Record<string, unknown> | null;
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
 *
 * Phase D extensions:
 * - **Advantage estimators** (canvas tile or `meta.advantage`) flow
 *   into `training.advantage`.
 * - **Stop-properly penalty coef** (`meta.stop_properly_penalty_coef`)
 *   flows into `training.stop_properly_penalty_coef`.
 * - **Policy backbones** picked via the meta-panel BackbonePicker
 *   (`meta.policy_kwargs`) are merged into the SB3 agent's
 *   `policy_kwargs` so the canonical `BackboneFeaturesExtractor`
 *   activates.
 * - **Weight-centric pipeline tiles** (`f_S/f_A/f_T/f_R`) on the
 *   canvas are bundled into the env's kwargs as `selector` /
 *   `allocator` / `timing` / `risk_overlay` build-specs so the
 *   runtime composes them via `WeightCentricPipeline`.
 */
export function serializeRLExperiment(
  graph: FlowGraph,
  meta: RLExperimentMeta,
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

  // Phase D: weight-centric pipeline tiles → fold into env kwargs.
  const envSpec = env ? buildSpecFor(env) : null;
  const pipelineNodes = graph.nodes.filter((n) => n.data.kind in WEIGHT_CENTRIC_KINDS);
  if (envSpec && pipelineNodes.length > 0) {
    const envKwargs: Record<string, unknown> = { ...envSpec.kwargs };
    for (const node of pipelineNodes) {
      const slot = WEIGHT_CENTRIC_KINDS[node.data.kind];
      if (!slot) continue;
      envKwargs[slot] = buildSpecFor(node);
    }
    envSpec.kwargs = envKwargs;
  }

  // Phase D: advantage estimator tile on the canvas takes precedence
  // over the meta-panel picker — author-on-canvas overrides author-
  // in-form (consistent with how reward terms work).
  const advantageNode = graph.nodes.find((n) => ADVANTAGE_KINDS.has(n.data.kind));
  const advantageSpec = advantageNode ? buildSpecFor(advantageNode) : meta.advantage ?? null;

  // Phase D: policy backbone tile on the canvas pushes a hint onto
  // the env extras so the agent picks it up; the meta-panel picker
  // shape (already a `policy_kwargs` block) is the canonical path.
  const agentSpec = agent ? buildSpecFor(agent) : null;
  if (agentSpec && meta.policy_kwargs) {
    const existingKwargs = (agentSpec.kwargs as Record<string, unknown>) ?? {};
    const existingPolicyKwargs = (existingKwargs.policy_kwargs as Record<string, unknown>) ?? {};
    agentSpec.kwargs = {
      ...existingKwargs,
      policy_kwargs: {
        ...existingPolicyKwargs,
        ...meta.policy_kwargs,
      },
    };
  } else if (agentSpec) {
    const backboneNode = graph.nodes.find((n) => BACKBONE_KINDS.has(n.data.kind));
    if (backboneNode) {
      const existingKwargs = (agentSpec.kwargs as Record<string, unknown>) ?? {};
      agentSpec.kwargs = {
        ...existingKwargs,
        _backbone_hint: buildSpecFor(backboneNode),
      };
    }
  }

  const training: Record<string, unknown> = {};
  if (advantageSpec) {
    training.advantage = advantageSpec;
  }
  if (meta.stop_properly_penalty_coef !== null && meta.stop_properly_penalty_coef !== undefined) {
    training.stop_properly_penalty_coef = meta.stop_properly_penalty_coef;
  }

  return {
    name: meta.name,
    ...(meta.description !== undefined ? { description: meta.description } : {}),
    env: envSpec,
    observation: observation ? { spec: buildSpecFor(observation) } : null,
    action: action ? { spec: buildSpecFor(action) } : null,
    reward: rewardSpec ? { spec: rewardSpec } : null,
    terminations: { specs: terminations },
    data_pipeline: dataPipeline ? { spec: buildSpecFor(dataPipeline) } : null,
    agent: agentSpec,
    ensembler: ensembler ? { spec: buildSpecFor(ensembler) } : null,
    experiment: experiment ? buildSpecFor(experiment) : null,
    ...(Object.keys(training).length > 0 ? { training } : {}),
  };
}
