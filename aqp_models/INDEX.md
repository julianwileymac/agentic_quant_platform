# aqp_models Index

## Live Implementation

- ML framework: `src/aqp_models/{base,dataset,handler,loader,planning,processors,recorder,splits,sampling,importance,bet_sizing}.py`.
- Workbench: `src/aqp_models/{flows,pipeline_recipes,walk_forward,experiments,alpha_backtest_experiment,alpha_metrics,factor_eval}.py`.
- Models: `src/aqp_models/models/`.
- Features: `src/aqp_models/features/`.
- Predictor Hub: `src/aqp_models/predictors/`.
- Adhoc helpers: `src/aqp_models/adhoc/`.
- Labeling: `src/aqp_models/labeling/`.
- Applications: `src/aqp_models/applications/`.
- Finetune: `src/aqp_models/finetune/`.
- Custom model serving: `src/aqp_models/serving/{vllm,ollama}.py`.
- Celery tasks: `tasks/{ml_tasks,ml_test_tasks,finetune_tasks,training_tasks}.py`.
- FastAPI routes: `api/routes/{ml,analytics_ml}.py`.
- Persistence models (in monolith): `../aqp/persistence/models_ml.py`,
  `../aqp/persistence/models_alpha_backtest.py`.
- Spec library: `configs/`.
- Canonical docs: `../aqp_docs/ml-framework.md`,
  `../aqp_docs/ml-libraries.md`, `../aqp_docs/ml-flows.md`,
  `../aqp_docs/ml-alpha-backtest.md`, `../aqp_docs/predictor-hub.md`.

## Model families

| Family | Module | Examples |
| --- | --- | --- |
| Tree | `models/tree.py` | LGBModel, XGBModel, CatBoostModel |
| Linear | `models/linear.py` | LinearModel |
| Sklearn pipeline | `models/sklearn.py` | SklearnRegressorModel, SklearnClassifierModel, SklearnPipelineModel |
| Forecasting | `models/forecasting.py` | ProphetForecastModel, SktimeForecastModel, SktimeReductionForecastModel |
| Anomaly | `models/anomaly.py` | PyODAnomalyModel |
| Naive Bayes | `models/naive_bayes.py` | NaiveBayesModel |
| Ensemble | `models/ensemble.py` | DEnsembleModel |
| HighFreq GBDT | `models/highfreq_gbdt.py` | HighFreqGBDTModel |
| Keras | `models/keras.py` | KerasMLPModel, KerasLSTMModel, KerasTabTransformerModel |
| TensorFlow | `models/tensorflow.py` | TFEstimatorDNNModel |
| HuggingFace | `models/huggingface.py` | HuggingFaceTextSignalModel, FinBERTSignal |
| SAE | `models/sae/` | KerasMLPRegressor (SAE wrapper) |
| SPM | `models/spm/` | TransformerForecaster, LSTMForecaster, ClassicalForecasters |
| Torch zoo | `models/torch/` | LSTM, Transformer, GRU, GATs, ALSTM, TCN, TabNet, etc. |
| Notebooks | `models/notebooks/` | LogisticWalkForward, RidgeVoC |

## Workbench flows

Registered in `flows.run_flow(...)` and surfaced in the webui drawer:

- `linear` — quick ridge / OLS regression workbench.
- `decomposition` — STL decomposition workbench.
- `forecast` — ARIMA / Prophet / Theta / AutoETS / sktime reduction.
- `garch` — ARCH / GARCH volatility diagnostics.
- `acf` — autocorrelation diagnostics.
- (Add new ones in `src/aqp_models/flows.py`.)

## Custom model serving

| Path | Backend | Use case |
| --- | --- | --- |
| `src/aqp_models/serving/vllm.py` | vLLM | In-process or self-hosted high-throughput LLM serving |
| `src/aqp_models/serving/ollama.py` | Ollama | Local OSS model pulling + serving |

The central LLM gateway (`router_complete`) stays in the monolith at
`../aqp/llm/providers/router.py`. This package owns model-pulling and
serving primitives, not the gateway.

## Future Extraction Gates

1. Define a stable HTTP / gRPC contract for the workbench `run_flow`
   surface so the monolith API gateway can call into a separate process.
2. Carve out persistence models (`ml_runs`, `ml_alpha_backtest_runs`,
   `ml_test_runs`, `finetune_runs`) into a shared schema so this
   boundary can run with its own ORM session.
3. Replace the direct dependency on `iceberg_catalog.append_arrow` with
   a thin client that respects the same medallion + business-metadata
   contract.
4. Replace the central registry import (`aqp.core.registry.register`)
   with a local registry mirror for the model class factory.

When all four are met, `aqp_models` is ready to extract into its own
repository per the Future Repo Split Gate in
[`../aqp_docs/repository-split.md`](../aqp_docs/repository-split.md).
