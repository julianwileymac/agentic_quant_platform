"""``WeightToOrders`` — translate target weight vector into broker orders.

Single canonical bridge between the RL policy output (a target weight
dict) and any registered :class:`IDomainBrokerage`. Mirrors the
``TargetWeightsRebalancer`` portfolio construction model used by the
backtest engines so the offline simulation and the live paper path
emit equivalent orders for the same ``w_t``.

Determinism contract
--------------------

For a given ``(target_weights, current_positions, current_prices,
equity)`` tuple the translator emits the same sequence of orders
every time. Kill-switch gating + rebalance threshold are the only
sources of non-determinism, and both are deterministic functions of
external state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WeightToOrdersResult:
    """Outcome of one :func:`apply_target_weights` invocation."""

    submitted_orders: list[Any] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    kill_switch_engaged: bool = False
    aborted: bool = False
    abort_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "submitted_orders": [getattr(o, "client_order_id", str(o)) for o in self.submitted_orders],
            "submitted_count": len(self.submitted_orders),
            "skipped": list(self.skipped),
            "kill_switch_engaged": bool(self.kill_switch_engaged),
            "aborted": bool(self.aborted),
            "abort_reason": self.abort_reason,
        }


class WeightToOrders:
    """Configurable translator from target weights to broker orders.

    Parameters
    ----------
    rebalance_threshold:
        Skip per-symbol rebalances where the absolute delta is below
        this fraction of total equity. Default ``0.005`` (50 bps).
    respect_kill_switch:
        When ``True`` (default) :func:`is_engaged` is checked before
        every order submission; engagement aborts the entire batch.
    """

    def __init__(
        self,
        *,
        rebalance_threshold: float = 0.005,
        respect_kill_switch: bool = True,
    ) -> None:
        self.rebalance_threshold = float(rebalance_threshold)
        self.respect_kill_switch = bool(respect_kill_switch)

    async def apply_async(
        self,
        *,
        brokerage: Any,
        target_weights: dict[str, float],
        current_prices: dict[str, float],
        equity: float | None = None,
    ) -> WeightToOrdersResult:
        if self.respect_kill_switch and self._kill_switch_engaged():
            logger.warning(
                "WeightToOrders: kill switch engaged; aborting weight application"
            )
            return WeightToOrdersResult(
                kill_switch_engaged=True,
                aborted=True,
                abort_reason="kill_switch_engaged",
            )

        positions = await self._fetch_positions(brokerage)
        if equity is None:
            equity = await self._infer_equity(brokerage, current_prices, positions)

        orders = self._build_orders(
            target_weights=target_weights,
            current_positions=positions,
            current_prices=current_prices,
            equity=float(equity),
        )

        submitted: list[Any] = []
        for order in orders:
            try:
                # IDomainBrokerage.submit is async.
                accepted = await brokerage.submit(order)
                submitted.append(accepted or order)
            except Exception:
                logger.exception(
                    "WeightToOrders: brokerage.submit failed for client_order_id=%s",
                    getattr(order, "client_order_id", None),
                )
        return WeightToOrdersResult(submitted_orders=submitted)

    # ------------------------------------------------------------------ helpers

    def _build_orders(
        self,
        *,
        target_weights: dict[str, float],
        current_positions: list[dict[str, Any]] | dict[str, float],
        current_prices: dict[str, float],
        equity: float,
    ) -> list[Any]:
        """Compute deltas + emit one :class:`DomainOrder` per symbol that needs rebalance."""
        import uuid

        from aqp.core.domain.enums import OrderSide
        from aqp.core.domain.identifiers import ClientOrderId, InstrumentId
        from aqp.core.domain.orders import MarketOrder

        # Normalise current_positions to {vt_symbol: signed_qty}.
        current_qty: dict[str, float] = {}
        if isinstance(current_positions, dict):
            current_qty = {k: float(v) for k, v in current_positions.items()}
        else:
            for pos in current_positions:
                vt = pos.get("vt_symbol") if isinstance(pos, dict) else getattr(pos, "vt_symbol", None)
                if vt is None:
                    continue
                qty = pos.get("quantity") if isinstance(pos, dict) else getattr(pos, "quantity", 0.0)
                side = pos.get("position_side") if isinstance(pos, dict) else getattr(pos, "position_side", None)
                sign = -1.0 if str(side or "").lower() in {"short", "sell"} else 1.0
                current_qty[str(vt)] = sign * float(qty or 0)

        orders: list[Any] = []
        all_symbols = set(target_weights) | set(current_qty)
        for vt in sorted(all_symbols):
            price = float(current_prices.get(vt, 0.0))
            if price <= 0:
                continue
            target_notional = float(target_weights.get(vt, 0.0)) * equity
            target_qty = target_notional / price
            delta = target_qty - float(current_qty.get(vt, 0.0))
            if abs(delta * price) < self.rebalance_threshold * equity:
                continue
            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            try:
                order = MarketOrder(
                    client_order_id=ClientOrderId(f"rl-{uuid.uuid4().hex[:12]}"),
                    instrument_id=InstrumentId.from_str(vt),
                    order_side=side,
                    quantity=Decimal(str(abs(delta))),
                    reduce_only=False,
                )
            except Exception:
                logger.exception("WeightToOrders: failed to construct MarketOrder for %s", vt)
                continue
            orders.append(order)
        return orders

    async def _fetch_positions(self, brokerage: Any) -> list[dict[str, Any]]:
        try:
            return await brokerage.fetch_positions()
        except Exception:
            logger.exception("WeightToOrders: brokerage.fetch_positions failed; assuming empty")
            return []

    async def _infer_equity(
        self,
        brokerage: Any,
        current_prices: dict[str, float],
        positions: list[dict[str, Any]],
    ) -> float:
        """Best-effort equity inference: cash + sum(qty * price)."""
        try:
            account = await brokerage.fetch_account()
            cash = float(getattr(account, "cash", 0.0) or 0.0)
        except Exception:
            cash = 0.0
        equity = cash
        for pos in positions:
            vt = pos.get("vt_symbol") if isinstance(pos, dict) else getattr(pos, "vt_symbol", None)
            qty = pos.get("quantity") if isinstance(pos, dict) else getattr(pos, "quantity", 0.0)
            if vt is None or vt not in current_prices:
                continue
            equity += float(qty or 0) * float(current_prices.get(vt, 0.0))
        return equity

    def _kill_switch_engaged(self) -> bool:
        try:
            from aqp.risk.kill_switch import is_engaged

            return bool(is_engaged())
        except Exception:
            logger.debug("WeightToOrders: kill switch probe failed; default disengaged", exc_info=True)
            return False


async def apply_target_weights(
    *,
    brokerage: Any,
    target_weights: dict[str, float],
    current_prices: dict[str, float],
    equity: float | None = None,
    rebalance_threshold: float = 0.005,
    respect_kill_switch: bool = True,
) -> WeightToOrdersResult:
    """Stateless façade around :class:`WeightToOrders` for one-shot use.

    Convenience wrapper for callers that don't need to retain the
    translator instance — typical pattern for paper-trading sessions
    that rebalance once per bar.
    """
    translator = WeightToOrders(
        rebalance_threshold=rebalance_threshold,
        respect_kill_switch=respect_kill_switch,
    )
    return await translator.apply_async(
        brokerage=brokerage,
        target_weights=target_weights,
        current_prices=current_prices,
        equity=equity,
    )


__all__ = [
    "WeightToOrders",
    "WeightToOrdersResult",
    "apply_target_weights",
]
