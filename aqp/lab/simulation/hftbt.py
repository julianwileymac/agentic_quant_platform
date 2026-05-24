"""``env='hftbt'`` simulation runner — wraps :class:`LobBacktestEngine`.

Phase 4 — inline runner reuses the Phase 2
:mod:`aqp.lab.executors.strategy_hftbt_market_maker` execution
surface so a Simulation-mode HFT run produces the same shape as
a Testing-mode run of the same strategy. The Dagster bridge in
:mod:`aqp.lab.executors._dagster_bridge` chooses between this
inline path and a real SandboxRuntime job depending on whether
``aqp.dagster.sandbox.runtime.SandboxRuntime`` is available.

The strategy callable is resolved either from a snippet id (the
Tier-2 gVisor sandbox runs the user's ``@njit`` strategy in Phase 4)
or from the default symmetric quoter in
:class:`strategy_hftbt_market_maker._SymmetricMarketMaker`.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aqp.lab.schema import GraphSpec

logger = logging.getLogger(__name__)


def run_hftbt_simulation(
    payload: dict[str, Any], *, spec: GraphSpec | None = None
) -> dict[str, Any]:
    """Run a market-making backtest in-process.

    Reads the simulation params off ``payload['extras']`` (which the
    Dagster bridge pipes verbatim from
    :attr:`SimulationConfig.extras`). When ``spec`` is supplied we
    pull strategy parameters off the first
    ``strategy.hftbt_market_maker`` node so the Simulation surface
    can reuse the user's Testing-mode strategy config.
    """
    started = time.time()
    extras = dict(payload.get("extras") or {})
    dataset_preset = extras.get("dataset_preset")
    if not dataset_preset and spec is not None:
        for node in spec.nodes:
            if node.type == "strategy.hftbt_market_maker":
                dataset_preset = (node.params or {}).get("dataset_preset")
                # Inherit defaults from the canvas node so the user
                # doesn't need to re-state them in the sim panel.
                for k in (
                    "half_spread_bps",
                    "inventory_target",
                    "inventory_gamma",
                    "max_events",
                    "latency_profile",
                    "queue_model",
                ):
                    extras.setdefault(k, (node.params or {}).get(k))
                break

    if not dataset_preset:
        return {
            "status": "error",
            "env": "hftbt",
            "error": (
                "hftbt simulation requires either SimulationConfig.extras.dataset_preset "
                "or a strategy.hftbt_market_maker node on the graph"
            ),
            "duration_ms": (time.time() - started) * 1000.0,
        }

    try:
        from aqp.lab.executors.strategy_hftbt_market_maker import (
            _SymmetricMarketMaker,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "env": "hftbt",
            "error": f"strategy_hftbt_market_maker import failed: {exc}",
            "duration_ms": (time.time() - started) * 1000.0,
        }
    try:
        from aqp.backtest.hft import LobBacktestEngine
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "env": "hftbt",
            "error": f"hftbacktest engine not importable: {exc}",
            "duration_ms": (time.time() - started) * 1000.0,
        }

    strategy = _SymmetricMarketMaker(
        half_spread_bps=float(extras.get("half_spread_bps") or 5.0),
        inventory_target=float(extras.get("inventory_target") or 0.0),
        inventory_gamma=float(extras.get("inventory_gamma") or 0.1),
    )
    engine = LobBacktestEngine()
    try:
        report = engine.run(
            strategy,
            dataset_preset=str(dataset_preset),
            latency_profile=str(extras.get("latency_profile") or "med"),
            queue_model=str(extras.get("queue_model") or "pro_rata"),
            max_events=int(extras.get("max_events") or 100_000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("hftbt simulation failed")
        return {
            "status": "error",
            "env": "hftbt",
            "error": f"LobBacktestEngine.run failed: {exc}",
            "duration_ms": (time.time() - started) * 1000.0,
        }

    summary: dict[str, Any] = {}
    if isinstance(report, dict):
        summary = {str(k): v for k, v in report.items()}
    else:
        for attr in (
            "events",
            "fills",
            "pnl",
            "max_drawdown",
            "sharpe",
            "fill_ratio",
            "queue_position",
        ):
            value = getattr(report, attr, None)
            if value is not None:
                summary[attr] = value

    return {
        "status": "done",
        "env": "hftbt",
        "dataset_preset": dataset_preset,
        "summary": summary,
        "duration_ms": (time.time() - started) * 1000.0,
    }


__all__ = ["run_hftbt_simulation"]
