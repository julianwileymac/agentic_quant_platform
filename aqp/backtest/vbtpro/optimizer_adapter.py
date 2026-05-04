"""Wrap ``vectorbtpro.portfolio.pfopt.PortfolioOptimizer`` as an AQP component.

vbt-pro ships a rich allocation-based optimisation surface
(``Portfolio.from_optimizer`` + ``PortfolioOptimizer`` factories such as
mean-variance, risk parity, equal weight, custom). This module adapts it
behind a thin AQP wrapper so:

- YAML configs can declare allocators with the standard ``class`` /
  ``module_path`` / ``kwargs`` factory.
- The vbt-pro engine's ``optimizer`` mode can resolve any registered
  allocator into a callable ``PortfolioOptimizer`` at run-time.
- Custom allocators (e.g. an LLM-driven weight-suggestion agent) plug in
  with the same shape.

When vbt-pro is unavailable, helper imports raise
:class:`VectorbtDependencyError` from
:mod:`aqp.backtest.vectorbt_backend` so users get an actionable error.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import pandas as pd

from aqp.backtest.vectorbt_backend import import_vectorbtpro
from aqp.core.registry import register

logger = logging.getLogger(__name__)


def _resolve_optimizer_class():
    vbt = import_vectorbtpro().module
    try:
        return vbt.PortfolioOptimizer  # type: ignore[attr-defined]
    except AttributeError:
        from vectorbtpro.portfolio.pfopt.base import PortfolioOptimizer  # type: ignore

        return PortfolioOptimizer


@register("EqualWeightOptimizer", kind="portfolio")
class EqualWeightOptimizer:
    """Allocate ``1 / n`` weight across every column of the close panel."""

    def __init__(self, *, every: str | int | None = None) -> None:
        self.every = every

    def build(self, close: pd.DataFrame) -> Any:
        opt_cls = _resolve_optimizer_class()
        return opt_cls.from_uniform(close=close, every=self.every)


@register("RandomWeightOptimizer", kind="portfolio")
class RandomWeightOptimizer:
    """Allocate Dirichlet-random weights — useful as a null hypothesis."""

    def __init__(self, *, every: str | int | None = None, seed: int | None = None) -> None:
        self.every = every
        self.seed = seed

    def build(self, close: pd.DataFrame) -> Any:
        opt_cls = _resolve_optimizer_class()
        kwargs: dict[str, Any] = {"close": close, "every": self.every}
        if self.seed is not None:
            kwargs["seed"] = self.seed
        return opt_cls.from_random(**kwargs)


@register("MeanVarianceOptimizer", kind="portfolio")
class MeanVarianceOptimizer:
    """Mean-variance allocator backed by vbt-pro / cvxportfolio.

    ``riskfolio_kwargs`` are forwarded to ``PortfolioOptimizer.from_riskfolio``
    if available, falling back to ``from_universal_returns`` for backends
    where Riskfolio-Lib is missing.
    """

    def __init__(
        self,
        *,
        every: str | int | None = "M",
        riskfolio_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.every = every
        self.riskfolio_kwargs = dict(riskfolio_kwargs or {})

    def build(self, close: pd.DataFrame) -> Any:
        opt_cls = _resolve_optimizer_class()
        kwargs = {"close": close, "every": self.every, **self.riskfolio_kwargs}
        if hasattr(opt_cls, "from_riskfolio"):
            return opt_cls.from_riskfolio(**kwargs)
        # Pre-Riskfolio fall-back: equal weight every rebalance period.
        return opt_cls.from_uniform(close=close, every=self.every)


@register("CallableOptimizer", kind="portfolio")
class CallableOptimizer:
    """Wrap an arbitrary ``(close, **kwargs) -> PortfolioOptimizer`` callable.

    Lets advanced users plug in a Python function (or an agent's weight-
    suggestion path) without writing a new registered class. The callable
    must return either a ``PortfolioOptimizer`` directly or a dict of
    weights with the same columns as ``close``.
    """

    def __init__(
        self,
        callable_path: str,
        *,
        every: str | int | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.callable_path = callable_path
        self.every = every
        self.kwargs = dict(kwargs or {})

    def _resolve(self) -> Callable[..., Any]:
        import importlib

        module_path, _, attr = self.callable_path.rpartition(".")
        if not module_path:
            raise ValueError(
                f"callable_path must be fully qualified (got {self.callable_path!r})"
            )
        return getattr(importlib.import_module(module_path), attr)

    def build(self, close: pd.DataFrame) -> Any:
        fn = self._resolve()
        result = fn(close, **self.kwargs)
        if isinstance(result, pd.DataFrame):
            opt_cls = _resolve_optimizer_class()
            return opt_cls.from_allocations(close=close, allocations=result, every=self.every)
        return result


def build_portfolio_from_optimizer(
    optimizer: Any,
    close: pd.DataFrame,
    *,
    init_cash: float = 100000.0,
    fees: float = 0.0005,
    slippage: float = 0.0002,
    extra_kwargs: dict[str, Any] | None = None,
) -> Any:
    """Drive ``Portfolio.from_optimizer`` from any AQP allocator.

    The ``optimizer`` argument is one of the registered classes above (or a
    duck-compatible object exposing ``.build(close)``). The returned object
    is a ``vbt.Portfolio`` instance.
    """
    vbt = import_vectorbtpro().module
    if hasattr(optimizer, "build"):
        pf_opt = optimizer.build(close)
    else:
        pf_opt = optimizer

    kwargs = dict(extra_kwargs or {})
    kwargs.setdefault("init_cash", init_cash)
    kwargs.setdefault("fees", fees)
    kwargs.setdefault("slippage", slippage)

    return vbt.Portfolio.from_optimizer(close, pf_opt, **kwargs)


__all__ = [
    "EqualWeightOptimizer",
    "RandomWeightOptimizer",
    "MeanVarianceOptimizer",
    "CallableOptimizer",
    "build_portfolio_from_optimizer",
]
