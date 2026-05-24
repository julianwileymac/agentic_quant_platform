"""Shared helpers for the TradeMaster-inspired ``tradesim_*`` envs.

These envs are ports of TradeMaster 1.0.0's domain envs into AQP's
:class:`BaseRLEnv` / metaclass conventions. The originals all
``pd.read_csv`` inside ``__init__`` which violates AGENTS hard rule 29
("envs read data via :class:`BaseDataset`"). This module ships a
small adapter that lets each env accept *either* a pandas DataFrame
directly (for tests + simple use) *or* a :class:`BaseDataset`
instance whose ``load()`` returns a DataFrame (for AQP integration).

The dual-input pattern preserves rule 29 (the env never reads a file
itself), while keeping the env testable in isolation with a fixture
DataFrame.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def coerce_to_dataframe(source: Any) -> pd.DataFrame:
    """Convert a flexible ``source`` argument into a pandas DataFrame.

    Accepted shapes:

    1. ``pd.DataFrame`` — returned as-is.
    2. Object with a ``load()`` method that returns a DataFrame
       (matches :class:`aqp.data.datasets.BaseDataset`).
    3. Object with a ``to_pandas()`` method (Arrow / Iceberg).
    4. Object with a ``data`` attribute holding a DataFrame.
    5. ``dict`` — passed to :func:`pd.DataFrame.from_dict`.

    Anything else raises :class:`TypeError`.
    """
    if isinstance(source, pd.DataFrame):
        return source
    if hasattr(source, "load") and callable(source.load):
        loaded = source.load()
        if isinstance(loaded, pd.DataFrame):
            return loaded
    if hasattr(source, "to_pandas") and callable(source.to_pandas):
        df = source.to_pandas()
        if isinstance(df, pd.DataFrame):
            return df
    if hasattr(source, "data") and isinstance(source.data, pd.DataFrame):
        return source.data
    if isinstance(source, dict):
        return pd.DataFrame.from_dict(source)
    raise TypeError(
        f"tradesim envs need pandas.DataFrame / BaseDataset / dict; "
        f"got {type(source).__name__}"
    )


def validate_columns(df: pd.DataFrame, required: Iterable[str]) -> None:
    """Raise :class:`ValueError` if ``df`` is missing any of ``required``."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"tradesim DataFrame is missing required columns: {missing}; "
            f"available: {list(df.columns)}"
        )


def stamp_step_info(
    info: dict[str, Any],
    *,
    portfolio_value: float,
    nav_return: float,
    t: int,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp the canonical AQP RL info contract onto ``info``.

    Every ``tradesim_*`` env's ``step`` returns ``info`` containing at
    least ``portfolio_value``, ``nav_return``, ``t`` (plus per-env
    extras). The :class:`RLRuntime` reads these to populate the
    Iceberg ``rl.equity_curves`` table without further plumbing.
    """
    info["portfolio_value"] = float(portfolio_value)
    info["nav_return"] = float(nav_return)
    info["t"] = int(t)
    if extras:
        info.update(extras)
    return info


def safe_pct_change(curr: float, prev: float) -> float:
    """Per-step return ``(curr - prev) / prev`` with zero-handling."""
    if prev <= 0:
        return 0.0
    return float((curr - prev) / prev)


def softmax_with_cash(logits: np.ndarray) -> np.ndarray:
    """Softmax ``logits`` so the output sums to 1 (used by EIIE / PM envs).

    Accepts ``(N+1,)`` logits (cash + N tickers); returns a same-shape
    probability vector. Numerically stable via the ``logits - max``
    trick.
    """
    arr = np.asarray(logits, dtype=np.float64).flatten()
    shifted = arr - float(arr.max())
    expd = np.exp(shifted)
    total = float(expd.sum())
    if total <= 0:
        # All non-finite ⇒ uniform fallback.
        return np.ones_like(arr) / max(len(arr), 1)
    return (expd / total).astype(np.float32)


def normalise_weights(weights: np.ndarray) -> np.ndarray:
    """Normalise a non-negative weight vector to sum to 1 (used after drift)."""
    arr = np.asarray(weights, dtype=np.float64).flatten()
    total = float(np.sum(arr))
    if total <= 0:
        return np.ones_like(arr) / max(len(arr), 1)
    return (arr / total).astype(np.float32)


__all__ = [
    "coerce_to_dataframe",
    "normalise_weights",
    "safe_pct_change",
    "softmax_with_cash",
    "stamp_step_info",
    "validate_columns",
]
