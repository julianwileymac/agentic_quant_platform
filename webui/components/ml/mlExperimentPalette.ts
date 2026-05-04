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

export const ML_EXPERIMENT_PALETTE: PaletteSection[] = [
  {
    title: "Source",
    items: [
      {
        kind: "Dataset",
        label: "Dataset",
        group: "Source",
        description: "DatasetH/TSDatasetH build config",
        defaultParams: { dataset_cfg: DEFAULT_DATASET_CFG },
      },
      {
        kind: "DatasetPreset",
        label: "Dataset preset",
        group: "Source",
        description: "Pull from a registered DatasetPreset (PRESETS)",
        defaultParams: { preset_name: "intraday_momentum_etf" },
      },
      {
        kind: "IcebergSlice",
        label: "Iceberg slice",
        group: "Source",
        description: "Read namespace.table for a (start, end, symbols) window",
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
        group: "Source",
        description: "Run a registered source.* fetcher to materialise bars",
        defaultParams: { node: "source.local_file", kwargs: {} },
      },
      {
        kind: "PipelineManifestRef",
        label: "Pipeline manifest",
        group: "Source",
        description: "Reference an existing PipelineManifestRow id",
        defaultParams: { pipeline_manifest_id: "" },
      },
      {
        kind: "FeatureSet",
        label: "Feature set",
        group: "Source",
        description: "Reference a saved FeatureSet id",
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
        group: "Pipeline",
        description: "Saved /ml/pipelines recipe id",
        defaultParams: { pipeline_recipe_id: "" },
      },
      {
        kind: "MLScale",
        label: "Scale",
        group: "Pipeline",
        description: "StandardScaler / RobustScaler / MinMaxScaler",
        defaultParams: { kwargs: { transformer: "standard" } },
      },
      {
        kind: "MLWinsorize",
        label: "Winsorize",
        group: "Pipeline",
        description: "Clip extreme values by quantile",
        defaultParams: { kwargs: { lower_q: 0.01, upper_q: 0.99 } },
      },
      {
        kind: "MLLag",
        label: "Lag features",
        group: "Pipeline",
        description: "Append lagged copies of selected columns",
        defaultParams: { kwargs: { columns: ["close"], lags: [1, 5, 20] } },
      },
      {
        kind: "MLRolling",
        label: "Rolling features",
        group: "Pipeline",
        description: "Rolling-window aggregates of selected columns",
        defaultParams: { kwargs: { columns: ["close"], windows: [5, 20, 60], aggregations: ["mean", "std"] } },
      },
      {
        kind: "MLDecompose",
        label: "Seasonal decompose",
        group: "Pipeline",
        description: "STL trend / seasonal / residual features",
        defaultParams: { kwargs: { column: "close", period: 20 } },
      },
      {
        kind: "MLPyODOutliers",
        label: "PyOD outliers",
        group: "Pipeline",
        description: "Drop rows flagged as outliers by a PyOD detector",
        defaultParams: { kwargs: { detector: "iforest", contamination: 0.02 } },
      },
      {
        kind: "MLImputation",
        label: "Imputation",
        group: "Pipeline",
        description: "Fill NaN values column-wise (mean/median/zero/last)",
        defaultParams: { kwargs: { strategy: "median" } },
      },
    ],
  },
  {
    title: "Split",
    items: [
      {
        kind: "Split",
        label: "Saved split plan",
        group: "Split",
        description: "Saved /ml/split-plans id",
        defaultParams: { split_plan_id: "" },
      },
      {
        kind: "WalkForward",
        label: "Walk-forward",
        group: "Split",
        description: "Rolling train/test windows",
        defaultParams: { train_periods: 252, test_periods: 21, step_periods: 21, anchored: false },
      },
      {
        kind: "PurgedKFold",
        label: "Purged K-Fold",
        group: "Split",
        description: "AFML purged k-fold with embargo",
        defaultParams: { n_splits: 5, embargo: 5 },
      },
      {
        kind: "Quarterly",
        label: "Quarterly PIT",
        group: "Split",
        description: "Point-in-time quarterly split for fundamentals",
        defaultParams: { train_quarters: 16, val_quarters: 4 },
      },
      {
        kind: "ChronologicalRatio",
        label: "Chronological ratio",
        group: "Split",
        description: "70/15/15 chronological split",
        defaultParams: { train_ratio: 0.7, val_ratio: 0.15 },
      },
    ],
  },
  {
    title: "Model",
    items: [
      {
        kind: "Model",
        label: "Model",
        group: "Model",
        description: "Registered AQP ML model config",
        defaultParams: {
          model_cfg: {
            class: "SklearnRegressorModel",
            module_path: "aqp.ml.models.sklearn",
            kwargs: { estimator: "ridge", estimator_kwargs: { alpha: 1.0 } },
          },
        },
      },
      {
        kind: "SklearnModel",
        label: "Sklearn model",
        group: "Model",
        description: "Sklearn regressor / classifier / pipeline / stacking",
        defaultParams: {
          model_cfg: {
            class: "SklearnRegressorModel",
            module_path: "aqp.ml.models.sklearn",
            kwargs: { estimator: "ridge", estimator_kwargs: { alpha: 1.0 } },
          },
        },
      },
      {
        kind: "KerasModel",
        label: "Keras model",
        group: "Model",
        description: "Keras MLP / LSTM / Functional / TabTransformer",
        defaultParams: {
          model_cfg: {
            class: "KerasMLPModel",
            module_path: "aqp.ml.models.keras",
            kwargs: { hidden_layers: [128, 64], dropout: 0.1, epochs: 20 },
          },
        },
      },
      {
        kind: "TensorflowModel",
        label: "TF Estimator",
        group: "Model",
        description: "Native TensorFlow tf.estimator (DNN / linear / boosted trees)",
        defaultParams: {
          model_cfg: {
            class: "TFEstimatorModel",
            module_path: "aqp.ml.models.tensorflow",
            kwargs: { estimator: "dnn", hidden_units: [64, 32], steps: 1000 },
          },
        },
      },
      {
        kind: "TorchModel",
        label: "Torch model",
        group: "Model",
        description: "qlib-style PyTorch module (LSTM / Transformer / TCN / GRU / TabNet / TRA / GATs / HIST)",
        defaultParams: {
          model_cfg: {
            class: "LSTMTSModel",
            module_path: "aqp.ml.models.torch.ts_aliases",
            kwargs: {},
          },
        },
      },
      {
        kind: "LightGBMModel",
        label: "LightGBM",
        group: "Model",
        description: "LightGBM gradient-boosted trees",
        defaultParams: {
          model_cfg: {
            class: "LGBModel",
            module_path: "aqp.ml.models.tree",
            kwargs: { num_leaves: 63, learning_rate: 0.05, n_estimators: 400 },
          },
        },
      },
      {
        kind: "XGBoostModel",
        label: "XGBoost",
        group: "Model",
        description: "XGBoost gradient-boosted trees",
        defaultParams: {
          model_cfg: {
            class: "XGBModel",
            module_path: "aqp.ml.models.tree",
            kwargs: { max_depth: 6, learning_rate: 0.05, n_estimators: 400 },
          },
        },
      },
      {
        kind: "ProphetModel",
        label: "Prophet",
        group: "Model",
        description: "Prophet forecaster",
        defaultParams: {
          model_cfg: {
            class: "ProphetForecastModel",
            module_path: "aqp.ml.models.forecasting",
            kwargs: { horizon: 20 },
          },
        },
      },
      {
        kind: "SktimeModel",
        label: "sktime",
        group: "Model",
        description: "sktime forecaster (AutoETS / AutoARIMA / Theta / Tbats)",
        defaultParams: {
          model_cfg: {
            class: "AutoETSForecastModel",
            module_path: "aqp.ml.models.forecasting",
            kwargs: { horizon: 20 },
          },
        },
      },
      {
        kind: "PyODModel",
        label: "PyOD anomaly",
        group: "Model",
        description: "PyOD anomaly detector",
        defaultParams: {
          model_cfg: {
            class: "PyODAnomalyModel",
            module_path: "aqp.ml.models.anomaly",
            kwargs: { detector: "iforest", contamination: 0.02 },
          },
        },
      },
      {
        kind: "HuggingFaceModel",
        label: "HuggingFace",
        group: "Model",
        description: "FinBERT sentiment / time-series transformer / generative",
        defaultParams: {
          model_cfg: {
            class: "HuggingFaceFinBertSentimentModel",
            module_path: "aqp.ml.models.huggingface",
            kwargs: {},
          },
        },
      },
    ],
  },
  {
    title: "Records",
    items: [
      {
        kind: "Records",
        label: "Records",
        group: "Records",
        description: "Record templates for alpha analysis",
        defaultParams: {
          records: [
            { class: "SigAnaRecord", module_path: "aqp.ml.recorder", kwargs: {} },
            { class: "PortAnaRecord", module_path: "aqp.ml.recorder", kwargs: {} },
          ],
        },
      },
      {
        kind: "SignalRecord",
        label: "Signal record",
        group: "Records",
        description: "Per-bar signal extraction",
        defaultParams: { records: [{ class: "SignalRecord", module_path: "aqp.ml.recorder", kwargs: {} }] },
      },
    ],
  },
  {
    title: "Experiment",
    items: [
      {
        kind: "Experiment",
        label: "Experiment",
        group: "Experiment",
        description: "Run name, experiment type, and target segment",
        defaultParams: {
          run_name: "builder-alpha-experiment",
          experiment_type: "alpha",
          segment: "test",
        },
      },
      {
        kind: "ForecastExperiment",
        label: "Forecast experiment",
        group: "Experiment",
        description: "Forecast-style metric rollup",
        defaultParams: { run_name: "builder-forecast-experiment", experiment_type: "forecast", segment: "test" },
      },
      {
        kind: "ClassificationExperiment",
        label: "Classification experiment",
        group: "Experiment",
        description: "Adds accuracy / precision / recall metrics",
        defaultParams: {
          run_name: "builder-classification-experiment",
          experiment_type: "classification",
          segment: "test",
        },
      },
      {
        kind: "AnomalyExperiment",
        label: "Anomaly experiment",
        group: "Experiment",
        description: "Anomaly score distribution metrics",
        defaultParams: { run_name: "builder-anomaly-experiment", experiment_type: "anomaly", segment: "test" },
      },
      {
        kind: "AlphaBacktestExperiment",
        label: "Alpha-backtest experiment",
        group: "Experiment",
        description: "Train + backtest in one run with combined ML+trading metrics",
        defaultParams: {
          run_name: "builder-alpha-backtest",
          segment: "test",
          train_first: true,
          strategy_cfg: {
            class: "MLStockSelectionAlpha",
            module_path: "aqp.strategies.ml_selection",
            kwargs: {
              alpha_model: {
                class: "DeployedModelAlpha",
                module_path: "aqp.strategies.ml_alphas",
                kwargs: {},
              },
            },
          },
          backtest_cfg: {
            class: "EventDrivenBacktester",
            module_path: "aqp.backtest.engine",
            kwargs: {
              start: "2024-01-01",
              end: "2024-12-31",
              initial_cash: 100000.0,
            },
          },
        },
      },
      {
        kind: "FlowPreview",
        label: "Flow Preview",
        group: "Experiment",
        description: "Lightweight linear/decomposition/forecast preview",
        defaultParams: { flow: "linear", estimator: "ridge", alpha: 1.0 },
      },
    ],
  },
  {
    title: "Test",
    items: [
      {
        kind: "SinglePredictTest",
        label: "Single predict",
        group: "Test",
        description: "Single-row inference against a deployment",
        defaultParams: { deployment_id: "", feature_row: {} },
      },
      {
        kind: "BatchPredictTest",
        label: "Batch predict",
        group: "Test",
        description: "Batch inference over an Iceberg slice",
        defaultParams: { deployment_id: "", symbols: ["AAPL"], start: "2024-01-01", end: "2024-06-30" },
      },
      {
        kind: "ABCompareTest",
        label: "A/B compare",
        group: "Test",
        description: "Compare two deployments side-by-side",
        defaultParams: { deployment_id_a: "", deployment_id_b: "", symbols: ["AAPL"] },
      },
      {
        kind: "ScenarioTest",
        label: "Scenario sweep",
        group: "Test",
        description: "Perturbation sensitivity table",
        defaultParams: { deployment_id: "", feature_row: {}, perturbations: [-0.1, 0, 0.1] },
      },
    ],
  },
  {
    title: "Deploy",
    items: [
      {
        kind: "RegisterModelVersion",
        label: "Register version",
        group: "Deploy",
        description: "Register a trained model in the MLflow registry",
        defaultParams: { registry_name: "" },
      },
      {
        kind: "PromoteToProduction",
        label: "Promote to Production",
        group: "Deploy",
        description: "Transition a registered model to the Production stage",
        defaultParams: { registry_name: "", version: "" },
      },
      {
        kind: "CreateModelDeployment",
        label: "Create deployment",
        group: "Deploy",
        description: "Spin up a ModelDeployment row + DeployedModelAlpha config",
        defaultParams: {
          name: "alpha-deploy",
          alpha_class: "DeployedModelAlpha",
          long_threshold: 0.001,
          short_threshold: -0.001,
          allow_short: true,
        },
      },
    ],
  },
];

export const ML_EXPERIMENT_ACCENTS: Record<string, string> = {
  // Source
  Dataset: "#14b8a6",
  DatasetPreset: "#14b8a6",
  IcebergSlice: "#0d9488",
  FetcherSource: "#0d9488",
  PipelineManifestRef: "#0e7490",
  FeatureSet: "#0e7490",
  // Pipeline
  Preprocessing: "#a78bfa",
  MLScale: "#a78bfa",
  MLWinsorize: "#a78bfa",
  MLLag: "#a78bfa",
  MLRolling: "#a78bfa",
  MLDecompose: "#a78bfa",
  MLPyODOutliers: "#a78bfa",
  MLImputation: "#a78bfa",
  // Split
  Split: "#38bdf8",
  WalkForward: "#38bdf8",
  PurgedKFold: "#38bdf8",
  Quarterly: "#38bdf8",
  ChronologicalRatio: "#38bdf8",
  // Model
  Model: "#f59e0b",
  SklearnModel: "#f59e0b",
  KerasModel: "#f59e0b",
  TensorflowModel: "#f59e0b",
  TorchModel: "#f59e0b",
  LightGBMModel: "#f59e0b",
  XGBoostModel: "#f59e0b",
  ProphetModel: "#f59e0b",
  SktimeModel: "#f59e0b",
  PyODModel: "#f59e0b",
  HuggingFaceModel: "#f59e0b",
  // Records
  Records: "#f97316",
  SignalRecord: "#f97316",
  // Experiment
  Experiment: "#22c55e",
  ForecastExperiment: "#22c55e",
  ClassificationExperiment: "#22c55e",
  AnomalyExperiment: "#22c55e",
  AlphaBacktestExperiment: "#16a34a",
  FlowPreview: "#ec4899",
  // Test
  SinglePredictTest: "#06b6d4",
  BatchPredictTest: "#06b6d4",
  ABCompareTest: "#06b6d4",
  ScenarioTest: "#06b6d4",
  // Deploy
  RegisterModelVersion: "#6366f1",
  PromoteToProduction: "#6366f1",
  CreateModelDeployment: "#6366f1",
};
