"""Regression diagnostics + heteroskedasticity tests.

Extends :func:`aqp.ml.flows.run_regression_diagnostics_flow` with the
three diagnostic tests the prompt asks for:

- White's test (general heteroskedasticity)
- Breusch-Pagan test (heteroskedasticity vs. regressors)
- Variance Inflation Factors (VIF) per regressor

Each is a thin wrapper around :mod:`statsmodels` so the lab can flag
spurious regressions before users fit OLS.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from pydantic import Field

from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


def _build_design(
    df: pd.DataFrame, *, target: str, features: list[str]
) -> tuple[pd.DataFrame, pd.Series]:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if target not in df.columns:
        raise ValueError(f"target column {target!r} not found")
    feats = [c for c in features if c in df.columns and c != target]
    if not feats:
        feats = [c for c in df.select_dtypes(include="number").columns if c != target]
    if not feats:
        raise ValueError("no numeric features available")
    sub = df[[*feats, target]].apply(pd.to_numeric, errors="coerce").dropna()
    return sub[feats], sub[target]


# ---------------------------------------------------------------------------
# OLS diagnostics (extends ml.flows variant)
# ---------------------------------------------------------------------------


class OLSDiagParams(FlowParams):
    target: str
    features: list[str] = Field(default_factory=list)
    add_constant: bool = True


@register_analysis_flow(
    name="regression.ols_diagnostics",
    namespace="regression",
    label="OLS diagnostics",
    description=(
        "Fit an OLS regression and report coefficients, standard errors, "
        "t-stats, p-values, R^2, F p-value, Durbin-Watson, AIC/BIC."
    ),
    params_model=OLSDiagParams,
    tags=("regression", "ols", "diagnostic"),
    optional_dependencies=("statsmodels",),
)
def ols_diagnostics_flow(
    df: pd.DataFrame, params: OLSDiagParams, ctx: FlowContext
) -> FlowResult:
    try:
        import statsmodels.api as sm
        from statsmodels.stats.stattools import durbin_watson
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc

    X, y = _build_design(df, target=params.target, features=params.features)
    if X.empty:
        return FlowResult(
            flow="regression.ols_diagnostics",
            metrics={"error": "no usable rows"},
        )
    Xc = sm.add_constant(X) if params.add_constant else X
    fit = sm.OLS(y, Xc).fit()
    rows: list[dict[str, Any]] = [
        {
            "feature": feat,
            "coef": float(fit.params.get(feat, 0.0)),
            "stderr": float(fit.bse.get(feat, 0.0)),
            "tvalue": float(fit.tvalues.get(feat, 0.0)),
            "pvalue": float(fit.pvalues.get(feat, 1.0)),
        }
        for feat in fit.params.index
    ]
    return FlowResult(
        flow="regression.ols_diagnostics",
        metrics={
            "rsquared": float(fit.rsquared),
            "rsquared_adj": float(fit.rsquared_adj),
            "f_pvalue": float(fit.f_pvalue),
            "durbin_watson": float(durbin_watson(fit.resid)),
            "aic": float(fit.aic),
            "bic": float(fit.bic),
            "n_obs": int(fit.nobs),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# White's test
# ---------------------------------------------------------------------------


class WhiteParams(FlowParams):
    target: str
    features: list[str] = Field(default_factory=list)


@register_analysis_flow(
    name="regression.white_test",
    namespace="regression",
    label="White's test",
    description=(
        "General heteroskedasticity test (regresses squared residuals "
        "on the original regressors and their cross-products)."
    ),
    params_model=WhiteParams,
    tags=("regression", "heteroskedasticity", "test"),
    optional_dependencies=("statsmodels",),
)
def white_test_flow(
    df: pd.DataFrame, params: WhiteParams, ctx: FlowContext
) -> FlowResult:
    try:
        import statsmodels.api as sm
        from statsmodels.stats.diagnostic import het_white
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc
    X, y = _build_design(df, target=params.target, features=params.features)
    if X.empty:
        return FlowResult(
            flow="regression.white_test",
            metrics={"error": "no usable rows"},
        )
    Xc = sm.add_constant(X)
    fit = sm.OLS(y, Xc).fit()
    lm, lm_pvalue, fvalue, f_pvalue = het_white(fit.resid, Xc)
    return FlowResult(
        flow="regression.white_test",
        metrics={
            "lm_statistic": float(lm),
            "lm_pvalue": float(lm_pvalue),
            "f_statistic": float(fvalue),
            "f_pvalue": float(f_pvalue),
            "n_obs": int(fit.nobs),
            "homoskedastic_05": bool(lm_pvalue > 0.05),
        },
    )


# ---------------------------------------------------------------------------
# Breusch-Pagan
# ---------------------------------------------------------------------------


class BreuschPaganParams(FlowParams):
    target: str
    features: list[str] = Field(default_factory=list)


@register_analysis_flow(
    name="regression.breusch_pagan",
    namespace="regression",
    label="Breusch-Pagan test",
    description=(
        "Tests heteroskedasticity by regressing squared OLS residuals "
        "on the original regressors. Lower p-value rejects homoskedasticity."
    ),
    params_model=BreuschPaganParams,
    tags=("regression", "heteroskedasticity", "test"),
    optional_dependencies=("statsmodels",),
)
def breusch_pagan_flow(
    df: pd.DataFrame, params: BreuschPaganParams, ctx: FlowContext
) -> FlowResult:
    try:
        import statsmodels.api as sm
        from statsmodels.stats.diagnostic import het_breuschpagan
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc
    X, y = _build_design(df, target=params.target, features=params.features)
    if X.empty:
        return FlowResult(
            flow="regression.breusch_pagan",
            metrics={"error": "no usable rows"},
        )
    Xc = sm.add_constant(X)
    fit = sm.OLS(y, Xc).fit()
    lm, lm_pvalue, fvalue, f_pvalue = het_breuschpagan(fit.resid, Xc)
    return FlowResult(
        flow="regression.breusch_pagan",
        metrics={
            "lm_statistic": float(lm),
            "lm_pvalue": float(lm_pvalue),
            "f_statistic": float(fvalue),
            "f_pvalue": float(f_pvalue),
            "n_obs": int(fit.nobs),
            "homoskedastic_05": bool(lm_pvalue > 0.05),
        },
    )


# ---------------------------------------------------------------------------
# VIF
# ---------------------------------------------------------------------------


class VIFParams(FlowParams):
    features: list[str] = Field(default_factory=list)
    threshold: float = Field(default=5.0, ge=1.0, le=100.0)


@register_analysis_flow(
    name="regression.vif",
    namespace="regression",
    label="Variance Inflation Factors",
    description=(
        "VIF per regressor. VIF > 5 indicates problematic multicollinearity. "
        "Computed via statsmodels.outliers_influence.variance_inflation_factor."
    ),
    params_model=VIFParams,
    tags=("regression", "multicollinearity"),
    optional_dependencies=("statsmodels",),
)
def vif_flow(
    df: pd.DataFrame, params: VIFParams, ctx: FlowContext
) -> FlowResult:
    try:
        import statsmodels.api as sm
        from statsmodels.stats.outliers_influence import variance_inflation_factor
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    feats = [c for c in params.features if c in df.columns]
    if not feats:
        feats = list(df.select_dtypes(include="number").columns)
    sub = df[feats].apply(pd.to_numeric, errors="coerce").dropna()
    if sub.empty or len(feats) < 2:
        return FlowResult(
            flow="regression.vif",
            metrics={"error": "need at least 2 features and non-empty rows"},
        )
    Xc = sm.add_constant(sub)
    rows: list[dict[str, Any]] = []
    for i, feat in enumerate(Xc.columns):
        if feat == "const":
            continue
        try:
            vif = float(variance_inflation_factor(Xc.values, i))
        except Exception:  # noqa: BLE001
            vif = float("nan")
        rows.append(
            {
                "feature": feat,
                "vif": vif,
                "above_threshold": bool(vif > float(params.threshold))
                if np.isfinite(vif)
                else False,
            }
        )
    n_above = sum(1 for r in rows if r["above_threshold"])
    return FlowResult(
        flow="regression.vif",
        metrics={
            "n_features": len(rows),
            "n_above_threshold": int(n_above),
            "threshold": float(params.threshold),
            "n_obs": int(len(sub)),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


__all__ = [
    "BreuschPaganParams",
    "OLSDiagParams",
    "VIFParams",
    "WhiteParams",
    "breusch_pagan_flow",
    "ols_diagnostics_flow",
    "vif_flow",
    "white_test_flow",
]
