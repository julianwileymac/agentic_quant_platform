"""HFT (LOB) strategy library.

Strategies subclass :class:`aqp.strategies.lob.LobStrategy` and run
through :class:`aqp.backtest.hft.LobBacktestEngine` (when the ``[hft]``
extra is installed) or via paper trading driven by the
``configs/paper/avellaneda_stoikov_quotes.yaml`` template.

Two strategies (:class:`GLFTMM`, :class:`AvellanedaStoikovMM`) consume
the JAX-compiled closed forms from
:mod:`aqp.optimal_control.avellaneda_stoikov` so their per-bar
``on_event`` bodies stay pure-Python.
"""
from __future__ import annotations

from aqp.strategies.hft.alphas import (
    AvellanedaStoikovMM,
    BasisAlphaMM,
    GLFTMM,
    GridMM,
    ImbalanceAlphaMM,
    QueueAwareMM,
)


__all__ = [
    "AvellanedaStoikovMM",
    "BasisAlphaMM",
    "GLFTMM",
    "GridMM",
    "ImbalanceAlphaMM",
    "QueueAwareMM",
]
