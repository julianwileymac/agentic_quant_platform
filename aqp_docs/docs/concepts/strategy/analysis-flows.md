---
title: 'Analysis Flows Reference'
summary: 'Every flow in the registry. Each flow is identified by a namespaced name (`namespace.flow`), declares a Pydantic params model, and returns a `FlowResult` with `metrics` / `rows` / `chart` / optional `...'
owner: strategy-team
last_reviewed: 2026-05-25
audience: both
---

# Analysis Flows Reference

> Framework: [aqp_docs/analysis-framework.md](../../concepts/strategy/analysis-framework.md) · UI: [aqp_docs/analysis-lab.md](../../concepts/strategy/analysis-lab.md).

Every flow in the registry. Each flow is identified by a namespaced
name (`namespace.flow`), declares a Pydantic params model, and returns
a `FlowResult` with `metrics` / `rows` / `chart` / optional
`arrow_table` for Iceberg persistence.

`GET /analysis/flows` lists every entry with the JSON-schema body
derived from the params model — the lab UI auto-renders forms from
this surface.

## profiling.\*

| Name | Label | Notes |
|---|---|---|
| `profiling.describe` | Column profile | Wraps `aqp.data.profiling.compute_profile` |
| `profiling.dtypes` | Dtypes | Per-column dtype + memory footprint |
| `profiling.null_audit` | Null audit | Null counts + null fractions |
| `profiling.topk` | Top-K values | Most-frequent values + share |

## distribution.\*

| Name | Label | Notes |
|---|---|---|
| `distribution.descriptive_stats` | Descriptive stats | Mean / median / std / skew / kurt / IQR / MAD / quantiles |
| `distribution.histogram` | Histogram | Equal-width bins + Plotly chart |
| `distribution.ecdf` | Empirical CDF | Sorted-value ECDF (down-sampled to `max_points`) |
| `distribution.qq_plot_points` | Q-Q plot points | Slope/intercept fit vs. norm/t/uniform/expon |
| `distribution.shapiro_wilk` | Shapiro-Wilk | Normality test (capped at 5000 samples) |
| `distribution.jarque_bera` | Jarque-Bera | Skew + kurt goodness-of-fit |
| `distribution.kolmogorov_smirnov` | K-S | One-sample vs reference dist (norm / t / uniform / expon / lognorm) |

## outlier.\*

| Name | Label | Notes |
|---|---|---|
| `outlier.zscore` | Z-score | Robust (median/MAD) or classical |
| `outlier.iqr` | IQR fences | Tukey ``[Q1 - kIQR, Q3 + kIQR]`` |
| `outlier.iforest` | Isolation Forest | sklearn |
| `outlier.dbscan` | DBSCAN | Density-based; `-1` is noise |
| `outlier.lof` | LOF | sklearn LocalOutlierFactor |
| `outlier.ecod` | ECOD | PyOD; falls back to z-score |
| `outlier.pulse_vs_step` | Pulse vs Step | Distinguish transient pulses from level shifts |

## imputation.\*

| Name | Label | Notes |
|---|---|---|
| `imputation.ffill_bfill` | Forward / backward fill | Default `ffill_then_bfill` |
| `imputation.linear` | Linear interpolation | pandas `axis=0` |
| `imputation.spline` | Cubic spline | pandas spline (order configurable) |
| `imputation.knn` | KNN imputer | sklearn `KNNImputer` |
| `imputation.mice` | MICE (IterativeImputer) | sklearn `IterativeImputer` |

## regression.\*

| Name | Label | Notes |
|---|---|---|
| `regression.ols_diagnostics` | OLS diagnostics | Coefs + SE + t / p + Durbin-Watson + AIC / BIC |
| `regression.white_test` | White's test | Heteroskedasticity (general form) |
| `regression.breusch_pagan` | Breusch-Pagan | Heteroskedasticity vs regressors |
| `regression.vif` | VIF | Variance Inflation Factors per regressor |

## time_series.\*

| Name | Label | Notes |
|---|---|---|
| `time_series.stl` | STL decomposition | Trend / seasonal / residual |
| `time_series.adf` | Augmented Dickey-Fuller | H0 = unit root |
| `time_series.kpss` | KPSS | H0 = stationary (ADF complement) |
| `time_series.acf_pacf` | ACF / PACF | Auto- and partial-autocorrelation series |
| `time_series.garch` | GARCH(p, q) | Volatility model + horizon variance forecast |
| `time_series.change_point` | Change-point | ruptures.KernelCPD with rbf kernel |
| `time_series.granger_causality` | Granger causality | Up to `max_lag` |
| `time_series.cointegration` | Engle-Granger | Pair cointegration |
| `time_series.spectral_fft` | Spectral (FFT) | Real FFT magnitude + power spectrum |
| `time_series.spectral_wavelet` | Continuous wavelet transform | PyWavelets (optional) |
| `time_series.hurst_exponent` | Hurst exponent | Long-range dependence |
| `time_series.theil_sen` | Theil-Sen slope | Robust median-of-pairwise-slopes |

## derivatives.\*

| Name | Label | Notes |
|---|---|---|
| `derivatives.bsm` | Black-Scholes-Merton | Closed-form European price + Greeks |
| `derivatives.greeks_surface` | Greeks surface | Δ/Γ/ν/Θ/ρ across strikes × expiries |
| `derivatives.implied_volatility` | Implied volatility (Brent) | Recover σ from a market quote |
| `derivatives.monte_carlo_european` | MC European option | Vectorised GBM; opt-in CUDA via cupy |
| `derivatives.monte_carlo_barrier` | MC barrier option | Knock-in / knock-out variants |
| `derivatives.monte_carlo_asian` | MC Asian option | Arithmetic / geometric averaging |
| `derivatives.sabr_smile` | SABR smile (Hagan) | Hagan-Kumar-Lesniewski-Woodward 2002 |
| `derivatives.bachelier` | Bachelier (normal model) | Wraps `aqp.options.normal_model` |

## portfolio.\*

| Name | Label | Notes |
|---|---|---|
| `portfolio.markowitz_efficient_frontier` | Efficient frontier | cvxpy if available, numpy-only fallback |
| `portfolio.ledoit_wolf_shrinkage` | Ledoit-Wolf covariance | Stabilised covariance matrix |
| `portfolio.fama_french_5_rolling` | FF5 rolling betas | Rolling-window OLS on Mkt-RF / SMB / HML / RMW / CMA |
| `portfolio.risk_parity` | Risk parity | Equal-risk-contribution weights (Spinu 2013) |

## factors.\*

| Name | Label | Notes |
|---|---|---|
| `factors.evaluate` | Factor evaluation | Wraps `aqp.data.factors.evaluate_factor` (IC + quantile spread + turnover) |

## microstructure.\*

| Name | Label | Notes |
|---|---|---|
| `microstructure.realised_volatility` | Realised volatility (OHLC) | Close-to-close / Parkinson / GK / RS / YZ |
| `microstructure.order_book_imbalance` | Order-book imbalance | Top-of-book |
| `microstructure.vpin` | VPIN | Wraps `aqp.data.microstructure.vpin` |

## Optional dependencies

Flows tag their optional deps (`optional_dependencies` field on the
descriptor). Missing extras raise a friendly `RuntimeError("install
extra X")` instead of crashing the catalog.

| Dep | Used by |
|---|---|
| `scikit-learn` | `outlier.{iforest,dbscan,lof}`, `imputation.{knn,mice}`, `portfolio.ledoit_wolf_shrinkage` |
| `statsmodels` | `regression.*`, `time_series.{adf,kpss,acf_pacf,granger_causality,cointegration,stl}` |
| `arch` | `time_series.garch` |
| `ruptures` | `time_series.change_point` |
| `pywavelets` | `time_series.spectral_wavelet` |
| `pyod` | `outlier.ecod` (falls back to z-score) |
| `cvxpy` | `portfolio.markowitz_efficient_frontier` (falls back to numpy projection) |
| `cupy` | `derivatives.monte_carlo_*` (opt-in GPU acceleration) |
