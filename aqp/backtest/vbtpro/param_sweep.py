"""Parameter sweeps on top of vbt-pro's ``Param`` machinery.

Two flavours:

- :func:`sweep_strategy_kwargs` — generic grid sweep over ``strategy.kwargs``
  paths. For each combination it materialises a fresh strategy and runs a
  full vbt-pro backtest, returning a wide ``DataFrame`` keyed by parameter
  combo and ranked by a chosen metric.
- :func:`sweep_signals_grid` — fast path for signal-only sweeps that uses
  ``vbt.Param`` natively to broadcast indicator parameter combinations and
  build a single ``Portfolio`` with a multi-column index. Mirrors the
  vbt-pro README "test 10,000 dual-SMA window combinations" pattern but
  generalised to any AQP-registered indicator.

This module integrates with the existing :class:`aqp.backtest.optimizer.ParameterSpec`
``trial_generator`` so existing optimisation flows can pass through unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd

from aqp.backtest.optimizer import ParameterSpec, generate_trials
from aqp.backtest.runner import run_backtest_from_config
from aqp.backtest.vbtpro.data_utils import filter_bars, pivot_close
from aqp.backtest.vectorbt_backend import import_vectorbtpro

logger = logging.getLogger(__name__)


@dataclass
class SweepResult:
    """Result of a parameter sweep — a ranked frame + best combo metadata."""

    frame: pd.DataFrame
    metric: str
    best_combo: dict[str, Any]
    best_value: float


def sweep_strategy_kwargs(
    base_config: dict[str, Any],
    param_grid: Mapping[str, Iterable[Any]],
    *,
    metric: str = "sharpe",
    method: str = "grid",
    n_trials: int | None = None,
    persist: bool = False,
    mlflow_log: bool = False,
) -> SweepResult:
    """Run a grid (or random) sweep over strategy kwargs.

    Each ``param_grid`` key is a dotted path inside ``base_config["strategy"]["kwargs"]``
    (e.g. ``"alpha_model.kwargs.lookback"``). Each value is the list of values
    to try.

    Parameters
    ----------
    base_config:
        Full strategy + backtest config (same shape as YAML). Defaults to
        ``mode="signals"`` if the engine isn't already vbt-pro.
    metric:
        Summary key to rank trials by — ``"sharpe"`` / ``"sortino"`` /
        ``"total_return"`` / ``"calmar"`` etc.
    method:
        ``"grid"`` (cartesian product) or ``"random"`` (uniform random
        sampling, requires ``n_trials``).
    n_trials:
        Required when ``method="random"``.
    persist / mlflow_log:
        Forwarded to :func:`run_backtest_from_config`. Defaults to False so
        sweeps don't bloat MLflow.
    """
    specs = [ParameterSpec(path=k, values=list(v)) for k, v in param_grid.items()]
    base_with_engine = _ensure_vbtpro(base_config)
    trial_iter = generate_trials(
        base_with_engine,
        specs,
        method=method,
        n_random=int(n_trials) if n_trials is not None else 32,
    )

    rows: list[dict[str, Any]] = []
    for i, (params, cfg) in enumerate(trial_iter):
        try:
            result = run_backtest_from_config(
                cfg,
                run_name=f"sweep_{i:04d}",
                persist=persist,
                mlflow_log=mlflow_log,
            )
        except Exception:
            logger.exception("sweep trial %d failed: %s", i, params)
            continue
        row = {
            "_trial": i,
            **params,
            **{
                k: result.get(k)
                for k in ("sharpe", "sortino", "total_return", "max_drawdown", "final_equity")
            },
        }
        rows.append(row)

    frame = pd.DataFrame(rows).sort_values(metric, ascending=False, na_position="last")
    if frame.empty:
        return SweepResult(frame=frame, metric=metric, best_combo={}, best_value=float("nan"))
    best = frame.iloc[0]
    best_combo = {k: best[k] for k in param_grid.keys() if k in best.index}
    return SweepResult(
        frame=frame.reset_index(drop=True),
        metric=metric,
        best_combo=best_combo,
        best_value=float(best.get(metric, float("nan"))),
    )


def sweep_signals_grid(
    bars: pd.DataFrame,
    strategy_cfg: dict[str, Any],
    *,
    fast_windows: Iterable[int] | None = None,
    slow_windows: Iterable[int] | None = None,
    init_cash: float = 100000.0,
    fees: float = 0.001,
    freq: str = "1D",
) -> pd.DataFrame:
    """Native vbt-pro ``Param`` MA-crossover sweep — fast path.

    Mirrors the vectorbt-pro README "test 10,000 dual-SMA window combinations"
    pattern. Returns a frame with one row per ``(fast, slow)`` combo and a
    ``total_return`` column ranked descending.

    For non-MA sweeps use :func:`sweep_strategy_kwargs`.
    """
    vbt = import_vectorbtpro().module
    fast_windows = list(fast_windows or [5, 10, 20])
    slow_windows = list(slow_windows or [50, 100, 200])

    frame = filter_bars(bars)
    close = pivot_close(frame)
    if close.shape[1] != 1:
        raise ValueError(
            "sweep_signals_grid requires a single-symbol bars frame; got "
            f"{close.shape[1]} columns."
        )
    series = close.iloc[:, 0]

    fast_ma = vbt.MA.run(series, window=fast_windows, short_name="fast")
    slow_ma = vbt.MA.run(series, window=slow_windows, short_name="slow")
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)
    pf = vbt.Portfolio.from_signals(
        series, entries, exits, init_cash=init_cash, fees=fees, freq=freq
    )
    try:
        total = pf.total_return()
    except Exception:
        total = pd.Series(dtype=float)
    if isinstance(total, pd.Series):
        out = total.to_frame("total_return").reset_index()
    else:
        out = pd.DataFrame({"total_return": [float(total)]})
    return out.sort_values("total_return", ascending=False, na_position="last").reset_index(drop=True)


def _ensure_vbtpro(cfg: dict[str, Any]) -> dict[str, Any]:
    bt_cfg = dict(cfg.get("backtest") or {})
    if "engine" not in bt_cfg and "class" not in bt_cfg:
        bt_cfg["engine"] = "vbt-pro:signals"
    out = dict(cfg)
    out["backtest"] = bt_cfg
    return out


__all__ = ["SweepResult", "sweep_strategy_kwargs", "sweep_signals_grid"]
