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

const MODEL_NODE_KINDS = new Set([
  "LightGBMModel",
  "XGBoostModel",
  "SklearnModel",
  "TorchModel",
  "KerasModel",
  "ProphetModel",
  "SktimeModel",
  "PyODModel",
  "HuggingFaceModel",
  "Model",
]);

const EXPERIMENT_KINDS = new Set([
  "ForecastExperiment",
  "ClassificationExperiment",
  "AnomalyExperiment",
  "Experiment",
]);

const DATASET_KINDS = new Set(["Dataset", "DatasetPreset", "IcebergSlice"]);
const SPLIT_KINDS = new Set(["WalkForward", "PurgedKFold", "ChronologicalRatio", "Split", "Quarterly"]);
const PREPROCESSING_KINDS = new Set([
  "Preprocessing",
  "MLScale",
  "MLWinsorize",
  "MLLag",
  "MLRolling",
  "MLDecompose",
]);

function paramsByAnyKind(graph: FlowGraph, kinds: Set<string>): Record<string, unknown> {
  const node = graph.nodes.find((n) => kinds.has(n.data.kind));
  return (node?.data.params ?? {}) as Record<string, unknown>;
}

function findNode(graph: FlowGraph, kinds: Set<string>) {
  return graph.nodes.find((n) => kinds.has(n.data.kind));
}

function defaultExperimentTypeForNode(kind: string): string {
  if (kind === "ForecastExperiment") return "forecast";
  if (kind === "ClassificationExperiment") return "classification";
  if (kind === "AnomalyExperiment") return "anomaly";
  return "alpha";
}

/**
 * Build the `/ml/experiment-runs` payload from a builder graph.
 * Throws when the canvas is missing a Dataset or a Model node.
 */
export function serializeMlExperiment(graph: FlowGraph): MlExperimentRequest {
  const dataset = paramsByAnyKind(graph, DATASET_KINDS);
  const split = paramsByAnyKind(graph, SPLIT_KINDS);
  const preprocessing = paramsByAnyKind(graph, PREPROCESSING_KINDS);
  const model = paramsByAnyKind(graph, MODEL_NODE_KINDS);
  const experimentNode = findNode(graph, EXPERIMENT_KINDS);
  const experiment = (experimentNode?.data.params ?? {}) as Record<string, unknown>;

  const dataset_cfg = (dataset.dataset_cfg as Record<string, unknown> | undefined) ?? {};
  const model_cfg = (model.model_cfg as Record<string, unknown> | undefined) ?? {};
  if (!Object.keys(dataset_cfg).length) {
    throw new Error("Add a Dataset node with a populated dataset_cfg");
  }
  if (!Object.keys(model_cfg).length) {
    throw new Error("Add a Model node with a populated model_cfg");
  }

  const experimentType = String(
    experiment.experiment_type ||
      defaultExperimentTypeForNode(experimentNode?.data.kind ?? "ForecastExperiment"),
  );

  return {
    dataset_cfg,
    model_cfg,
    run_name: String(experiment.run_name || "builder-ml-experiment"),
    experiment_type: experimentType,
    segment: String(experiment.segment || "test"),
    records: [],
    split_plan_id: (split.split_plan_id as string) || null,
    pipeline_recipe_id: (preprocessing.pipeline_recipe_id as string) || null,
    dataset_version_id: (dataset.dataset_version_id as string) || null,
    experiment_plan_id: (experiment.experiment_plan_id as string) || null,
  };
}
