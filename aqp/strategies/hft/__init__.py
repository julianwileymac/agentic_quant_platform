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
from aqp.strategies.hft.automated_technical_search import (
    BootstrapTechSearchAlpha,
    TechnicalRule,
    bootstrap_baseline,
    evaluate_rule,
    search_rules,
)
from aqp.strategies.hft.microprice import MicropriceAlpha
from aqp.strategies.hft.obi_directional import OBIDirectionalAlpha
from aqp.strategies.hft.obizhaeva_wang_exec import ObizhaevaWangExecution


__all__ = [
    "AvellanedaStoikovMM",
    "BasisAlphaMM",
    "BootstrapTechSearchAlpha",
    "GLFTMM",
    "GridMM",
    "ImbalanceAlphaMM",
    "MicropriceAlpha",
    "OBIDirectionalAlpha",
    "ObizhaevaWangExecution",
    "QueueAwareMM",
    "TechnicalRule",
    "bootstrap_baseline",
    "evaluate_rule",
    "search_rules",
]
