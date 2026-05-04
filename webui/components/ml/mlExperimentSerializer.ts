import type { FlowGraph } from "@/components/flow/types";

export interface MlExperimentRequest {
  dataset_cfg: Record<string, unknown>;
  model_cfg: Record<string, unknown>;
  run_name: string;
  experiment_type: string;
  segment: string;
  records?: unknown[];
  split_plan_id?: string | null;
  pipeline_recipe_id?: string | null;
  dataset_version_id?: string | null;
  experiment_plan_id?: string | null;
}

export interface AlphaBacktestRequest {
  strategy_cfg: Record<string, unknown>;
  backtest_cfg: Record<string, unknown>;
  dataset_cfg?: Record<string, unknown>;
  model_cfg?: Record<string, unknown>;
  run_name: string;
  segment: string;
  train_first: boolean;
  deployment_id?: string | null;
  records?: unknown[];
  split_plan_id?: string | null;
  pipeline_recipe_id?: string | null;
  experiment_plan_id?: string | null;
}

export type SerializedDispatch =
  | { kind: "ml_experiment"; payload: MlExperimentRequest; endpoint: "/ml/experiment-runs" }
  | { kind: "alpha_backtest"; payload: AlphaBacktestRequest; endpoint: "/ml/alpha-backtest-runs" }
  | { kind: "test_single"; payload: Record<string, unknown>; endpoint: "/ml/test/single" }
  | { kind: "test_batch"; payload: Record<string, unknown>; endpoint: "/ml/test/batch" }
  | { kind: "test_compare"; payload: Record<string, unknown>; endpoint: "/ml/test/compare" }
  | { kind: "test_scenario"; payload: Record<string, unknown>; endpoint: "/ml/test/scenario" };

const MODEL_NODE_KINDS = new Set([
  "Model",
  "SklearnModel",
  "KerasModel",
  "TensorflowModel",
  "TorchModel",
  "LightGBMModel",
  "XGBoostModel",
  "ProphetModel",
  "SktimeModel",
  "PyODModel",
  "HuggingFaceModel",
]);

const EXPERIMENT_KINDS = new Set([
  "Experiment",
  "ForecastExperiment",
  "ClassificationExperiment",
  "AnomalyExperiment",
]);

const TEST_KINDS = new Set([
  "SinglePredictTest",
  "BatchPredictTest",
  "ABCompareTest",
  "ScenarioTest",
]);

function paramsByKind(graph: FlowGraph, kind: string): Record<string, unknown> {
  const node = graph.nodes.find((n) => n.data.kind === kind);
  return (node?.data.params ?? {}) as Record<string, unknown>;
}

function paramsByAnyKind(graph: FlowGraph, kinds: Set<string>): Record<string, unknown> {
  const node = graph.nodes.find((n) => kinds.has(n.data.kind));
  return (node?.data.params ?? {}) as Record<string, unknown>;
}

function findNode(graph: FlowGraph, predicate: (kind: string) => boolean) {
  return graph.nodes.find((n) => predicate(n.data.kind));
}

function defaultExperimentTypeForNode(kind: string): string {
  if (kind === "ForecastExperiment") return "forecast";
  if (kind === "ClassificationExperiment") return "classification";
  if (kind === "AnomalyExperiment") return "anomaly";
  return "alpha";
}

export function serializeMlExperiment(graph: FlowGraph): MlExperimentRequest {
  const dataset = paramsByAnyKind(graph, new Set(["Dataset", "DatasetPreset", "IcebergSlice"]));
  const split = paramsByAnyKind(graph, new Set(["Split", "WalkForward", "PurgedKFold", "Quarterly", "ChronologicalRatio"]));
  const preprocessing = paramsByAnyKind(graph, new Set(["Preprocessing"]));
  const model = paramsByAnyKind(graph, MODEL_NODE_KINDS);
  const records = paramsByKind(graph, "Records");
  const experimentNode = findNode(graph, (k) => EXPERIMENT_KINDS.has(k));
  const experiment = (experimentNode?.data.params ?? {}) as Record<string, unknown>;

  const dataset_cfg = (dataset.dataset_cfg as Record<string, unknown> | undefined) ?? {};
  const model_cfg = (model.model_cfg as Record<string, unknown> | undefined) ?? {};
  if (!Object.keys(dataset_cfg).length) {
    throw new Error("Add a Dataset node with dataset_cfg");
  }
  if (!Object.keys(model_cfg).length) {
    throw new Error("Add a Model node with model_cfg");
  }

  const experimentType = String(
    experiment.experiment_type || defaultExperimentTypeForNode(experimentNode?.data.kind ?? "Experiment"),
  );

  return {
    dataset_cfg,
    model_cfg,
    run_name: String(experiment.run_name || "builder-ml-experiment"),
    experiment_type: experimentType,
    segment: String(experiment.segment || "test"),
    records: Array.isArray(records.records) ? records.records : [],
    split_plan_id: (split.split_plan_id as string) || null,
    pipeline_recipe_id: (preprocessing.pipeline_recipe_id as string) || null,
    dataset_version_id: (dataset.dataset_version_id as string) || null,
    experiment_plan_id: (experiment.experiment_plan_id as string) || null,
  };
}

export function serializeAlphaBacktest(graph: FlowGraph): AlphaBacktestRequest {
  const dataset = paramsByAnyKind(graph, new Set(["Dataset", "DatasetPreset", "IcebergSlice"]));
  const model = paramsByAnyKind(graph, MODEL_NODE_KINDS);
  const split = paramsByAnyKind(graph, new Set(["Split", "WalkForward", "PurgedKFold"]));
  const preprocessing = paramsByAnyKind(graph, new Set(["Preprocessing"]));
  const ab = paramsByKind(graph, "AlphaBacktestExperiment");
  const dataset_cfg = (dataset.dataset_cfg as Record<string, unknown> | undefined) ?? {};
  const model_cfg = (model.model_cfg as Record<string, unknown> | undefined) ?? {};
  const strategy_cfg = (ab.strategy_cfg as Record<string, unknown> | undefined) ?? {};
  const backtest_cfg = (ab.backtest_cfg as Record<string, unknown> | undefined) ?? {};
  if (!Object.keys(strategy_cfg).length) {
    throw new Error("AlphaBacktestExperiment node requires strategy_cfg");
  }
  if (!Object.keys(backtest_cfg).length) {
    throw new Error("AlphaBacktestExperiment node requires backtest_cfg");
  }
  const train_first = Boolean(ab.train_first ?? true);
  if (train_first && !Object.keys(model_cfg).length) {
    throw new Error("AlphaBacktestExperiment with train_first=true requires a Model node");
  }
  return {
    strategy_cfg,
    backtest_cfg,
    dataset_cfg: train_first ? dataset_cfg : undefined,
    model_cfg: train_first ? model_cfg : undefined,
    run_name: String(ab.run_name || "builder-alpha-backtest"),
    segment: String(ab.segment || "test"),
    train_first,
    deployment_id: (ab.deployment_id as string) || null,
    split_plan_id: (split.split_plan_id as string) || null,
    pipeline_recipe_id: (preprocessing.pipeline_recipe_id as string) || null,
    experiment_plan_id: (ab.experiment_plan_id as string) || null,
  };
}

export function serializeFlowPreview(graph: FlowGraph): { flow: string; payload: Record<string, unknown> } {
  const dataset = paramsByAnyKind(graph, new Set(["Dataset", "DatasetPreset", "IcebergSlice"]));
  const preview = paramsByKind(graph, "FlowPreview");
  const flow = String(preview.flow || "linear");
  return {
    flow,
    payload: {
      ...preview,
      dataset_cfg: dataset.dataset_cfg ?? {},
    },
  };
}

export function dispatchFromGraph(graph: FlowGraph): SerializedDispatch {
  const hasAlphaBacktest = graph.nodes.some((n) => n.data.kind === "AlphaBacktestExperiment");
  if (hasAlphaBacktest) {
    return {
      kind: "alpha_backtest",
      payload: serializeAlphaBacktest(graph),
      endpoint: "/ml/alpha-backtest-runs",
    };
  }
  const testNode = findNode(graph, (k) => TEST_KINDS.has(k));
  if (testNode) {
    const params = (testNode.data.params ?? {}) as Record<string, unknown>;
    if (testNode.data.kind === "SinglePredictTest") {
      return { kind: "test_single", payload: { ...params, sync: true }, endpoint: "/ml/test/single" };
    }
    if (testNode.data.kind === "BatchPredictTest") {
      return { kind: "test_batch", payload: params, endpoint: "/ml/test/batch" };
    }
    if (testNode.data.kind === "ABCompareTest") {
      return { kind: "test_compare", payload: params, endpoint: "/ml/test/compare" };
    }
    if (testNode.data.kind === "ScenarioTest") {
      return { kind: "test_scenario", payload: { ...params, sync: true }, endpoint: "/ml/test/scenario" };
    }
  }
  return {
    kind: "ml_experiment",
    payload: serializeMlExperiment(graph),
    endpoint: "/ml/experiment-runs",
  };
}
