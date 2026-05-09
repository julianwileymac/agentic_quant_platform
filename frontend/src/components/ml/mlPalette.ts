import type { PaletteSection } from "@/components/flow/types";

const DEFAULT_DATASET_CFG = {
  class: "DatasetH",
  module_path: "aqp.ml.dataset",
  kwargs: {
    handler: {
      class: "Alpha158",
      module_path: "aqp.ml.features.alpha158",
      kwargs: {
        instruments: ["SPY", "AAPL", "MSFT"],
        start_time: "2019-01-01",
        end_time: "2024-12-31",
      },
    },
    segments: {
      train: ["2019-01-01", "2022-12-31"],
      valid: ["2023-01-01", "2023-12-31"],
      test: ["2024-01-01", "2024-12-31"],
    },
  },
};

/**
 * Distilled ML Builder palette. Kind discriminators are preserved
 * so legacy specs round-trip, but we keep one canonical tile per
 * concept rather than the full 30+-tile legacy catalogue. The
 * `defaultParams` shapes match what the legacy serializer expects.
 */
export const ML_PALETTE: PaletteSection[] = [
  {
    title: "Source",
    items: [
      {
        kind: "Dataset",
        label: "Dataset (Alpha158)",
        description: "DatasetH/TSDatasetH build config",
        accent: "#06b6d4",
        defaultParams: { dataset_cfg: DEFAULT_DATASET_CFG },
      },
      {
        kind: "DatasetPreset",
        label: "Dataset preset",
        description: "Pull from PRESETS",
        accent: "#06b6d4",
        defaultParams: { preset_name: "intraday_momentum_etf" },
      },
      {
        kind: "IcebergSlice",
        label: "Iceberg slice",
        description: "namespace.table over (start, end, symbols)",
        accent: "#06b6d4",
        defaultParams: {
          iceberg_identifier: "aqp_alpha_vantage.time_series_daily_adjusted",
          start: "2024-01-01",
          end: "2024-12-31",
          symbols: ["AAPL"],
        },
      },
      {
        kind: "FetcherSource",
        label: "Fetcher source",
        accent: "#06b6d4",
        defaultParams: { node: "source.local_file", kwargs: {} },
      },
      {
        kind: "FeatureSet",
        label: "Feature set ref",
        accent: "#06b6d4",
        defaultParams: { feature_set_id: "" },
      },
    ],
  },
  {
    title: "Pipeline",
    items: [
      {
        kind: "Preprocessing",
        label: "Saved recipe",
        accent: "#3b82f6",
        defaultParams: { pipeline_recipe_id: "" },
      },
      {
        kind: "MLScale",
        label: "Scale",
        description: "Standard / Robust / MinMax",
        accent: "#3b82f6",
        defaultParams: { kwargs: { transformer: "standard" } },
      },
      {
        kind: "MLWinsorize",
        label: "Winsorize",
        accent: "#3b82f6",
        defaultParams: { kwargs: { lower_q: 0.01, upper_q: 0.99 } },
      },
      {
        kind: "MLLag",
        label: "Lag features",
        accent: "#3b82f6",
        defaultParams: { kwargs: { columns: ["close"], lags: [1, 5, 20] } },
      },
      {
        kind: "MLRolling",
        label: "Rolling features",
        accent: "#3b82f6",
        defaultParams: {
          kwargs: { columns: ["close"], windows: [5, 20, 60], aggregations: ["mean", "std"] },
        },
      },
      {
        kind: "MLDecompose",
        label: "Seasonal decompose",
        accent: "#3b82f6",
        defaultParams: { kwargs: { column: "close", period: 20 } },
      },
    ],
  },
  {
    title: "Split",
    items: [
      {
        kind: "WalkForward",
        label: "Walk-forward",
        accent: "#a855f7",
        defaultParams: { kwargs: { train_window: 252, test_window: 63, step: 21 } },
      },
      {
        kind: "PurgedKFold",
        label: "Purged K-fold",
        accent: "#a855f7",
        defaultParams: { kwargs: { n_splits: 5, embargo: 5 } },
      },
      {
        kind: "ChronologicalRatio",
        label: "Chronological ratio",
        accent: "#a855f7",
        defaultParams: { kwargs: { train_ratio: 0.7, valid_ratio: 0.15 } },
      },
    ],
  },
  {
    title: "Model",
    items: [
      {
        kind: "LightGBMModel",
        label: "LightGBM",
        accent: "#22c55e",
        defaultParams: {
          model_cfg: {
            class: "LightGBMModel",
            module_path: "aqp.ml.models.lightgbm",
            kwargs: { n_estimators: 200, learning_rate: 0.05, max_depth: 6 },
          },
        },
      },
      {
        kind: "XGBoostModel",
        label: "XGBoost",
        accent: "#22c55e",
        defaultParams: {
          model_cfg: {
            class: "XGBoostModel",
            module_path: "aqp.ml.models.xgboost",
            kwargs: { n_estimators: 200, learning_rate: 0.05, max_depth: 6 },
          },
        },
      },
      {
        kind: "SklearnModel",
        label: "Sklearn",
        accent: "#22c55e",
        defaultParams: {
          model_cfg: {
            class: "SklearnModel",
            module_path: "aqp.ml.models.sklearn",
            kwargs: { estimator: "RandomForestRegressor", n_estimators: 200 },
          },
        },
      },
      {
        kind: "TorchModel",
        label: "PyTorch",
        accent: "#22c55e",
        defaultParams: {
          model_cfg: {
            class: "TorchModel",
            module_path: "aqp.ml.models.torch",
            kwargs: { architecture: "LSTM", hidden_size: 64, num_layers: 2 },
          },
        },
      },
      {
        kind: "KerasModel",
        label: "Keras",
        accent: "#22c55e",
        defaultParams: {
          model_cfg: {
            class: "KerasModel",
            module_path: "aqp.ml.models.keras",
            kwargs: { architecture: "LSTM" },
          },
        },
      },
    ],
  },
  {
    title: "Experiment",
    items: [
      {
        kind: "ForecastExperiment",
        label: "Forecast",
        accent: "#f59e0b",
        defaultParams: { experiment_type: "forecast", run_name: "ml-forecast", segment: "test" },
      },
      {
        kind: "ClassificationExperiment",
        label: "Classification",
        accent: "#f59e0b",
        defaultParams: { experiment_type: "classification", run_name: "ml-cls", segment: "test" },
      },
      {
        kind: "AnomalyExperiment",
        label: "Anomaly",
        accent: "#f59e0b",
        defaultParams: { experiment_type: "anomaly", run_name: "ml-anomaly", segment: "test" },
      },
    ],
  },
  {
    title: "Test",
    items: [
      {
        kind: "SinglePredictTest",
        label: "Single predict",
        accent: "#ef4444",
        defaultParams: { records: [] },
      },
      {
        kind: "BatchPredictTest",
        label: "Batch predict",
        accent: "#ef4444",
        defaultParams: { records: [] },
      },
      {
        kind: "ABCompareTest",
        label: "A/B compare",
        accent: "#ef4444",
        defaultParams: { deployment_id_a: "", deployment_id_b: "" },
      },
    ],
  },
];

export const ML_NODE_ACCENTS: Record<string, string> = {
  Dataset: "#06b6d4",
  DatasetPreset: "#06b6d4",
  IcebergSlice: "#06b6d4",
  FetcherSource: "#06b6d4",
  FeatureSet: "#06b6d4",
  Preprocessing: "#3b82f6",
  MLScale: "#3b82f6",
  MLWinsorize: "#3b82f6",
  MLLag: "#3b82f6",
  MLRolling: "#3b82f6",
  MLDecompose: "#3b82f6",
  WalkForward: "#a855f7",
  PurgedKFold: "#a855f7",
  ChronologicalRatio: "#a855f7",
  LightGBMModel: "#22c55e",
  XGBoostModel: "#22c55e",
  SklearnModel: "#22c55e",
  TorchModel: "#22c55e",
  KerasModel: "#22c55e",
  ForecastExperiment: "#f59e0b",
  ClassificationExperiment: "#f59e0b",
  AnomalyExperiment: "#f59e0b",
  SinglePredictTest: "#ef4444",
  BatchPredictTest: "#ef4444",
  ABCompareTest: "#ef4444",
};
