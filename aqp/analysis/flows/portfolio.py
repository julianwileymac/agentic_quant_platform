"""Portfolio construction + risk-attribution flows.

Catalogue:

- ``portfolio.markowitz_efficient_frontier`` — quadratic-program frontier.
- ``portfolio.ledoit_wolf_shrinkage`` — stabilised covariance matrix.
- ``portfolio.fama_french_5_rolling`` — rolling FF5 OLS exposures.
- ``portfolio.risk_parity`` — equal-risk-contribution weights.

The frontier solver tries cvxpy first and falls back to a
closed-form long-only solution that requires only numpy when cvxpy
is unavailable. The Fama-French data fetcher is best-effort: if the
Ken French CSV cannot be reached, the flow returns a structured
error instead of crashing.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field

from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _returns_matrix(
    df: pd.DataFrame,
    *,
    return_columns: list[str] | None = None,
    panel_id_column: str | None = None,
    panel_value_column: str | None = None,
    panel_date_column: str | None = None,
) -> pd.DataFrame:
    """Project a long or wide frame into a wide returns matrix.

    Three layouts supported:

    1. Wide: ``return_columns`` exist as columns of ``df``.
    2. Long: ``panel_id_column`` + ``panel_value_column`` (+ optional
       ``panel_date_column``) — pivot to wide.
    3. Default: numeric columns minus ``panel_*`` columns.
    """
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if return_columns:
        cols = [c for c in return_columns if c in df.columns]
        out = df[cols].apply(pd.to_numeric, errors="coerce")
        return out.dropna(how="all")
    if panel_id_column and panel_value_column:
        date_col = panel_date_column or "timestamp"
        if date_col not in df.columns:
            df = df.reset_index().rename(columns={"index": date_col})
        out = (
            df.pivot_table(
                index=date_col,
                columns=panel_id_column,
                values=panel_value_column,
                aggfunc="last",
            )
            .apply(pd.to_numeric, errors="coerce")
        )
        return out
    out = df.select_dtypes(include="number").apply(pd.to_numeric, errors="coerce")
    return out


# ---------------------------------------------------------------------------
# Markowitz efficient frontier
# ---------------------------------------------------------------------------


class MarkowitzParams(FlowParams):
    return_columns: list[str] = Field(default_factory=list)
    panel_id_column: str | None = None
    panel_value_column: str | None = None
    panel_date_column: str | None = None
    n_points: int = Field(default=21, ge=3, le=200)
    long_only: bool = True
    min_weight: float = 0.0
    max_weight: float = 1.0
    risk_free_rate: float = 0.0


@register_analysis_flow(
    name="portfolio.markowitz_efficient_frontier",
    namespace="portfolio",
    label="Efficient frontier",
    description=(
        "Compute the long-only mean-variance efficient frontier across "
        "the supplied return columns. Uses cvxpy when available and a "
        "numpy-only quadratic projection otherwise."
    ),
    params_model=MarkowitzParams,
    tags=("portfolio", "mvo"),
    optional_dependencies=("cvxpy",),
)
def markowitz_flow(
    df: pd.DataFrame, params: MarkowitzParams, ctx: FlowContext
) -> FlowResult:
    rets = _returns_matrix(
        df,
        return_columns=params.return_columns,
        panel_id_column=params.panel_id_column,
        panel_value_column=params.panel_value_column,
        panel_date_column=params.panel_date_column,
    )
    rets = rets.dropna(axis=1, how="all").dropna(how="any")
    if rets.shape[1] < 2 or rets.shape[0] < 5:
        return FlowResult(
            flow="portfolio.markowitz_efficient_frontier",
            error="need at least 2 columns and 5 rows of returns",
        )
    mu = rets.mean().to_numpy(dtype=float)
    sigma = np.cov(rets.values.T, ddof=1)
    n_assets = mu.size

    target_returns = np.linspace(mu.min(), mu.max(), int(params.n_points))
    rows: list[dict[str, Any]] = []

    backend = "cvxpy"
    try:
        import cvxpy as cp  # type: ignore[import-not-found]

        weights = cp.Variable(n_assets)
        target = cp.Parameter()
        constraints = [cp.sum(weights) == 1.0]
        if params.long_only:
            constraints.append(weights >= max(0.0, params.min_weight))
        else:
            constraints.append(weights >= float(params.min_weight))
        constraints.append(weights <= float(params.max_weight))
        constraints.append(mu @ weights >= target)
        prob = cp.Problem(cp.Minimize(cp.quad_form(weights, cp.psd_wrap(sigma))), constraints)
        for r in target_returns:
            target.value = float(r)
            try:
                prob.solve(warm_start=True)
            except Exception:  # noqa: BLE001
                continue
            if weights.value is None:
                continue
            w = np.asarray(weights.value).ravel()
            port_mean = float(mu @ w)
            port_var = float(w.T @ sigma @ w)
            rows.append(_frontier_row(rets.columns, w, port_mean, port_var, params))
    except Exception:  # noqa: BLE001
        backend = "numpy_fallback"
        for r in target_returns:
            w = _projected_weights(mu, sigma, target=float(r), long_only=params.long_only)
            if w is None:
                continue
            port_mean = float(mu @ w)
            port_var = float(w.T @ sigma @ w)
            rows.append(_frontier_row(rets.columns, w, port_mean, port_var, params))

    if not rows:
        return FlowResult(
            flow="portfolio.markowitz_efficient_frontier",
            error="solver could not produce any feasible portfolio",
            metrics={"backend": backend},
        )

    chart = {
        "data": [
            {
                "type": "scatter",
                "mode": "lines+markers",
                "x": [r["volatility"] for r in rows],
                "y": [r["expected_return"] for r in rows],
                "name": "frontier",
            }
        ],
        "layout": {
            "title": "Mean-variance efficient frontier",
            "xaxis": {"title": "volatility"},
            "yaxis": {"title": "expected return"},
        },
    }
    return FlowResult(
        flow="portfolio.markowitz_efficient_frontier",
        metrics={
            "n_assets": n_assets,
            "n_points": len(rows),
            "backend": backend,
        },
        rows=rows,
        chart=chart,
        arrow_table=coerce_arrow(rows),
    )


def _frontier_row(
    columns: pd.Index,
    weights: np.ndarray,
    port_mean: float,
    port_var: float,
    params: MarkowitzParams,
) -> dict[str, Any]:
    vol = math.sqrt(max(port_var, 0.0))
    sharpe = (
        (port_mean - params.risk_free_rate) / vol if vol > 0 else 0.0
    )
    weight_payload = {f"w_{c}": float(w) for c, w in zip(columns, weights, strict=False)}
    return {
        "expected_return": port_mean,
        "volatility": vol,
        "variance": port_var,
        "sharpe": sharpe,
        **weight_payload,
    }


def _projected_weights(
    mu: np.ndarray,
    sigma: np.ndarray,
    *,
    target: float,
    long_only: bool,
) -> np.ndarray | None:
    """Closed-form long-only frontier via projected gradient.

    Solves ``min 0.5 w'Σw`` s.t. ``μ'w >= target`` and ``Σ w = 1``,
    plus ``w >= 0`` when long_only. Iterative projection — fine for
    small ``n_assets`` (<=50) which is what the lab UI handles.
    """
    n = mu.size
    w = np.full(n, 1.0 / n, dtype=float)
    lr = 0.05
    for _ in range(800):
        grad = sigma @ w - lr * mu
        w = w - lr * grad
        if long_only:
            w = np.maximum(w, 0.0)
        s = w.sum()
        if s <= 0:
            return None
        w = w / s
        if mu @ w >= target:
            break
    if not (math.isfinite(float(mu @ w)) and math.isfinite(float(w @ sigma @ w))):
        return None
    return w


# ---------------------------------------------------------------------------
# Ledoit-Wolf shrinkage
# ---------------------------------------------------------------------------


class LedoitWolfParams(FlowParams):
    return_columns: list[str] = Field(default_factory=list)
    panel_id_column: str | None = None
    panel_value_column: str | None = None
    panel_date_column: str | None = None


@register_analysis_flow(
    name="portfolio.ledoit_wolf_shrinkage",
    namespace="portfolio",
    label="Ledoit-Wolf covariance",
    description=(
        "Stabilise the empirical covariance via Ledoit-Wolf shrinkage. "
        "Returns the shrinkage intensity + condition number improvement."
    ),
    params_model=LedoitWolfParams,
    tags=("portfolio", "covariance", "shrinkage"),
    optional_dependencies=("scikit-learn",),
)
def ledoit_wolf_flow(
    df: pd.DataFrame, params: LedoitWolfParams, ctx: FlowContext
) -> FlowResult:
    try:
        from sklearn.covariance import LedoitWolf
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "scikit-learn is not installed. Install via the `ml` extra."
        ) from exc
    rets = _returns_matrix(
        df,
        return_columns=params.return_columns,
        panel_id_column=params.panel_id_column,
        panel_value_column=params.panel_value_column,
        panel_date_column=params.panel_date_column,
    ).dropna(axis=1, how="all").dropna(how="any")
    if rets.shape[1] < 2 or rets.shape[0] < 5:
        return FlowResult(
            flow="portfolio.ledoit_wolf_shrinkage",
            error="need at least 2 columns and 5 rows of returns",
        )
    arr = rets.to_numpy(dtype=float)
    sample = np.cov(arr.T, ddof=1)
    lw = LedoitWolf().fit(arr)
    cov = lw.covariance_
    cond_sample = float(np.linalg.cond(sample)) if sample.size else float("nan")
    cond_shrunk = float(np.linalg.cond(cov)) if cov.size else float("nan")
    columns = list(rets.columns)
    rows = [
        {
            "row": columns[i],
            "col": columns[j],
            "sample_cov": float(sample[i, j]),
            "shrunk_cov": float(cov[i, j]),
        }
        for i in range(len(columns))
        for j in range(len(columns))
    ]
    return FlowResult(
        flow="portfolio.ledoit_wolf_shrinkage",
        metrics={
            "n_assets": len(columns),
            "shrinkage": float(lw.shrinkage_),
            "cond_sample": cond_sample,
            "cond_shrunk": cond_shrunk,
            "frobenius_diff": float(np.linalg.norm(sample - cov)),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Fama-French rolling exposures
# ---------------------------------------------------------------------------


class FF5RollingParams(FlowParams):
    asset_column: str = Field(..., description="Asset return column inside df")
    date_column: str = "timestamp"
    window: int = Field(default=60, ge=10, le=2000)
    factors_url: str | None = None
    factors_csv_path: str | None = None


@register_analysis_flow(
    name="portfolio.fama_french_5_rolling",
    namespace="portfolio",
    label="Fama-French 5 rolling betas",
    description=(
        "Rolling-window OLS regression of asset returns on the FF5 "
        "factors (Mkt-RF, SMB, HML, RMW, CMA). Tries Ken French's "
        "public CSV; falls back to user-supplied factors_csv_path."
    ),
    params_model=FF5RollingParams,
    tags=("portfolio", "factors", "fama_french"),
)
def fama_french_5_rolling_flow(
    df: pd.DataFrame, params: FF5RollingParams, ctx: FlowContext
) -> FlowResult:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if params.asset_column not in df.columns:
        return FlowResult(
            flow="portfolio.fama_french_5_rolling",
            error=f"asset column {params.asset_column!r} not found",
        )
    factors = _load_ff5(
        url=params.factors_url, local_path=params.factors_csv_path
    )
    if factors is None or factors.empty:
        return FlowResult(
            flow="portfolio.fama_french_5_rolling",
            error="could not load FF5 factor frame",
        )
    asset = (
        df[[params.date_column, params.asset_column]]
        .rename(columns={params.asset_column: "ret"})
        .copy()
    )
    asset[params.date_column] = pd.to_datetime(asset[params.date_column], errors="coerce")
    asset = asset.dropna()
    merged = asset.merge(
        factors.reset_index(),
        left_on=params.date_column,
        right_on=factors.index.name or "Date",
        how="inner",
    )
    if merged.empty:
        return FlowResult(
            flow="portfolio.fama_french_5_rolling",
            error="no overlap between asset returns and FF5 factors",
        )
    factor_cols = [c for c in ("Mkt-RF", "SMB", "HML", "RMW", "CMA") if c in merged.columns]
    if not factor_cols:
        return FlowResult(
            flow="portfolio.fama_french_5_rolling",
            error="no FF5 factor columns recognised in fetched frame",
        )
    rf = merged.get("RF", pd.Series(0.0, index=merged.index))
    excess = merged["ret"] - rf
    rows = []
    window = int(params.window)
    for i in range(window, len(merged)):
        sl = merged.iloc[i - window : i]
        y = (sl["ret"] - sl.get("RF", 0.0)).to_numpy(dtype=float)
        X = sl[factor_cols].to_numpy(dtype=float)
        Xc = np.column_stack([np.ones(len(X)), X])
        try:
            coef, *_ = np.linalg.lstsq(Xc, y, rcond=None)
        except Exception:  # noqa: BLE001
            continue
        rows.append(
            {
                "timestamp": str(merged[params.date_column].iloc[i]),
                "alpha": float(coef[0]),
                **{
                    name: float(coef[idx + 1])
                    for idx, name in enumerate(factor_cols)
                },
            }
        )
    if not rows:
        return FlowResult(
            flow="portfolio.fama_french_5_rolling",
            error="not enough overlapping rows for the requested window",
        )
    metrics = {
        "n_obs": int(len(merged)),
        "window": window,
        "n_rolling_estimates": len(rows),
        "factor_columns": factor_cols,
        "mean_alpha": float(np.mean([r["alpha"] for r in rows])),
    }
    for col in factor_cols:
        metrics[f"mean_{col}"] = float(np.mean([r[col] for r in rows]))
    return FlowResult(
        flow="portfolio.fama_french_5_rolling",
        metrics=metrics,
        rows=rows[-500:],
        arrow_table=coerce_arrow(rows),
    )


def _load_ff5(*, url: str | None, local_path: str | None) -> pd.DataFrame | None:
    """Best-effort FF5 daily factor loader.

    Tries (in order):

    1. ``local_path`` if provided.
    2. ``url`` if provided.
    3. Ken French daily 5-factor CSV (zipped) as a fallback. Network
       errors are caught and logged; the caller surfaces a graceful
       FlowResult error.
    """
    candidates = []
    if local_path:
        candidates.append(local_path)
    if url:
        candidates.append(url)
    candidates.append(
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
        "ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
    )
    for src in candidates:
        try:
            frame = _read_ff5_csv(src)
            if frame is not None and not frame.empty:
                return frame
        except Exception:  # noqa: BLE001
            logger.debug("FF5 load failed for %s", src, exc_info=True)
            continue
    return None


def _read_ff5_csv(src: str) -> pd.DataFrame | None:
    if src.endswith(".zip"):
        import io
        from urllib.request import urlopen
        from zipfile import ZipFile

        with urlopen(src, timeout=10) as resp:  # noqa: S310 - http for ken-french data
            blob = resp.read()
        with ZipFile(io.BytesIO(blob)) as zf:
            name = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
            if name is None:
                return None
            with zf.open(name) as f:
                raw = f.read().decode("latin-1")
    else:
        with open(src, encoding="latin-1") as f:
            raw = f.read()
    rows: list[list[str]] = []
    started = False
    for line in raw.splitlines():
        clean = line.strip()
        if not clean:
            if started:
                break
            continue
        parts = [p.strip() for p in clean.split(",")]
        if not started and parts[0].lower().startswith("date"):
            started = True
            header = parts
            continue
        if started:
            try:
                int(parts[0])
            except (ValueError, IndexError):
                break
            rows.append(parts)
    if not rows:
        return None
    frame = pd.DataFrame(rows, columns=header)
    frame[header[0]] = pd.to_datetime(frame[header[0]], format="%Y%m%d", errors="coerce")
    frame = frame.dropna(subset=[header[0]]).set_index(header[0])
    frame.index.name = "Date"
    for col in frame.columns:
        frame[col] = pd.to_numeric(frame[col], errors="coerce") / 100.0
    return frame


# ---------------------------------------------------------------------------
# Risk parity
# ---------------------------------------------------------------------------


class RiskParityParams(FlowParams):
    return_columns: list[str] = Field(default_factory=list)
    panel_id_column: str | None = None
    panel_value_column: str | None = None
    panel_date_column: str | None = None
    iterations: int = Field(default=200, ge=10, le=10_000)
    tolerance: float = Field(default=1e-8, ge=1e-12, le=1e-2)


@register_analysis_flow(
    name="portfolio.risk_parity",
    namespace="portfolio",
    label="Risk parity",
    description=(
        "Equal-risk-contribution weights via Spinu (2013) iterative "
        "Newton-style solver. Long-only, sums to 1."
    ),
    params_model=RiskParityParams,
    tags=("portfolio", "risk_parity"),
)
def risk_parity_flow(
    df: pd.DataFrame, params: RiskParityParams, ctx: FlowContext
) -> FlowResult:
    rets = _returns_matrix(
        df,
        return_columns=params.return_columns,
        panel_id_column=params.panel_id_column,
        panel_value_column=params.panel_value_column,
        panel_date_column=params.panel_date_column,
    ).dropna(axis=1, how="all").dropna(how="any")
    if rets.shape[1] < 2 or rets.shape[0] < 5:
        return FlowResult(
            flow="portfolio.risk_parity",
            error="need at least 2 columns and 5 rows of returns",
        )
    sigma = np.cov(rets.values.T, ddof=1)
    n = sigma.shape[0]
    w = np.full(n, 1.0 / n, dtype=float)
    target = 1.0 / n
    for _ in range(int(params.iterations)):
        sigma_w = sigma @ w
        port_var = float(w @ sigma_w)
        if port_var <= 0:
            break
        risk_contributions = w * sigma_w / port_var
        diff = risk_contributions - target
        if np.max(np.abs(diff)) < float(params.tolerance):
            break
        w = w - 0.5 * diff
        w = np.maximum(w, 1e-12)
        w = w / w.sum()
    sigma_w = sigma @ w
    port_var = float(w @ sigma_w)
    rc = (w * sigma_w / port_var) if port_var > 0 else np.full(n, 1.0 / n)
    columns = list(rets.columns)
    rows = [
        {
            "asset": columns[i],
            "weight": float(w[i]),
            "risk_contribution": float(rc[i]),
        }
        for i in range(n)
    ]
    return FlowResult(
        flow="portfolio.risk_parity",
        metrics={
            "n_assets": n,
            "portfolio_volatility": float(math.sqrt(max(port_var, 0.0))),
            "iterations": int(params.iterations),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


_ = pd  # keep import alive for IDE-friendliness


__all__ = [
    "FF5RollingParams",
    "LedoitWolfParams",
    "MarkowitzParams",
    "RiskParityParams",
    "fama_french_5_rolling_flow",
    "ledoit_wolf_flow",
    "markowitz_flow",
    "risk_parity_flow",
]
