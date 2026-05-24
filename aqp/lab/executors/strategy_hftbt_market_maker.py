"""``strategy.hftbt_market_maker`` — LOB market-making backtest.

Phase 2 ships a lightweight inline runner that wraps
:class:`aqp.backtest.hft.LobBacktestEngine` with a simple symmetric
quote strategy (Avellaneda-Stoikov-style: mid +/- ``half_spread`` x
``vol_estimate``). Phase 4 swaps the strategy callable for a
user-authored ``@njit`` snippet resolved through the Tier-2 gVisor
sandbox per AGENTS rule 45 + plan §4. Both paths share the same
output_locator shape so downstream consumers (Simulation panel,
``out.tearsheet``, ``out.publish_mlflow``) don't care which path
ran.

Params:

- ``dataset_preset`` (str, required) — passed verbatim to
  :meth:`LobBacktestEngine.run`. Matches the dataset_preset keys
  used by the existing ``/backtest/lob`` route.
- ``half_spread_bps`` (float, default 5.0) — quoting half-spread in
  basis points of mid.
- ``inventory_target`` (float, default 0.0) — penalise positions
  away from this target so the engine reverts to flat.
- ``inventory_gamma`` (float, default 0.1) — penalty weight (γ in
  Avellaneda-Stoikov).
- ``max_events`` (int, default 100_000) — bound the replay.
- ``latency_profile`` (str, default 'med').
- ``queue_model`` (str, default 'pro_rata').
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    dataset_preset = params.get("dataset_preset")
    if not dataset_preset:
        return NodeResult(
            status="error",
            error="strategy.hftbt_market_maker requires params.dataset_preset",
            log_label="strategy.hftbt_market_maker:missing_preset",
        )

    half_spread_bps = float(params.get("half_spread_bps") or 5.0)
    inventory_target = float(params.get("inventory_target") or 0.0)
    inventory_gamma = float(params.get("inventory_gamma") or 0.1)
    max_events = int(params.get("max_events") or 100_000)
    latency_profile = str(params.get("latency_profile") or "med")
    queue_model = str(params.get("queue_model") or "pro_rata")

    try:
        from aqp.backtest.hft import LobBacktestEngine
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"hftbacktest engine not importable: {exc}",
            log_label="strategy.hftbt_market_maker:no_engine",
        )

    strategy = _SymmetricMarketMaker(
        half_spread_bps=half_spread_bps,
        inventory_target=inventory_target,
        inventory_gamma=inventory_gamma,
    )
    engine = LobBacktestEngine()
    try:
        report = engine.run(
            strategy,
            dataset_preset=str(dataset_preset),
            latency_profile=latency_profile,
            queue_model=queue_model,
            max_events=max_events,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("hftbacktest run failed")
        return NodeResult(
            status="error",
            error=f"LobBacktestEngine.run failed: {exc}",
            log_label="strategy.hftbt_market_maker:run_fail",
        )

    summary = _coerce_summary(report)
    equity = summary.pop("equity_curve", [])
    return NodeResult(
        status="done",
        output_locator={
            "kind": "portfolio_summary",
            "engine": "hftbacktest",
            "dataset_preset": dataset_preset,
            "stats": summary,
            "equity_curve": equity[:5_000],
            "node_id": node.id,
        },
        metrics={
            "events": int(summary.get("events", 0)),
            "fills": int(summary.get("fills", 0)),
            "pnl": float(summary.get("pnl", 0.0)),
            "max_drawdown": float(summary.get("max_drawdown", 0.0)),
            "sharpe": float(summary.get("sharpe", 0.0)),
        },
        log_label=f"strategy.hftbt_market_maker:{dataset_preset}",
    )


class _SymmetricMarketMaker:
    """Avellaneda-Stoikov-style symmetric quoting strategy.

    Implemented in pure Python for Phase 2 (no @njit). The Tier-2
    sandbox in Phase 4 will swap this for a user-authored
    ``@njit`` callable resolved from a snippet id.
    """

    def __init__(
        self,
        *,
        half_spread_bps: float,
        inventory_target: float,
        inventory_gamma: float,
    ) -> None:
        self.half_spread = half_spread_bps / 10_000.0
        self.inventory_target = float(inventory_target)
        self.inventory_gamma = float(inventory_gamma)
        self.name = "lab.hftbt_market_maker"

    def on_book(self, mid: float, inventory: float) -> tuple[float, float]:
        """Return (bid, ask) quotes given a mid price + inventory."""
        skew = self.inventory_gamma * (inventory - self.inventory_target)
        reservation = mid - skew
        bid = reservation * (1.0 - self.half_spread)
        ask = reservation * (1.0 + self.half_spread)
        return bid, ask


def _coerce_summary(report: Any) -> dict[str, Any]:
    """Normalise the engine's report into a flat dict the Lab can render."""
    if report is None:
        return {}
    if isinstance(report, dict):
        return {str(k): v for k, v in report.items()}
    out: dict[str, Any] = {}
    for attr in (
        "events",
        "fills",
        "pnl",
        "max_drawdown",
        "sharpe",
        "fill_ratio",
        "queue_position",
        "n_orders",
    ):
        value = getattr(report, attr, None)
        if value is not None:
            out[attr] = value
    equity = getattr(report, "equity_curve", None)
    if equity is None and hasattr(report, "to_dict"):
        try:
            d = report.to_dict()
            return {str(k): v for k, v in d.items()}
        except Exception:  # noqa: BLE001
            pass
    if equity is not None:
        try:
            out["equity_curve"] = list(equity)
        except Exception:  # noqa: BLE001
            pass
    return out


__all__ = ["execute"]
