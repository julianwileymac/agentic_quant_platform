"""FastAPI app for the out-of-band pre-trade risk service.

Runs as a separate K8s Deployment owned by the broker-dealer
ServiceAccount (per § 240.15c3-5(d)). Provides a synchronous Layer-2
check that aggregates credit + capital across every bot in a fleet,
plus a metadata listing of the configured policies.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def create_risk_service_app(
    *,
    engine: Any | None = None,
    fleet_id: str = "default",
) -> Any:
    """Build the FastAPI app.

    Lazy-imports FastAPI so the package remains importable even in
    environments without FastAPI installed (e.g. the operator-only
    image which only needs the policy / kill-switch surface).
    """
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel, Field
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI required for create_risk_service_app; install with "
            "pip install fastapi"
        ) from exc

    if engine is None:
        from aqp_bots.risk.engine import PreTradeRiskEngine

        engine = PreTradeRiskEngine(check_kill_switch=True)

    app = FastAPI(
        title="QuantBot Pre-Trade Risk Service",
        version="0.2.0",
        description=(
            "Layer-2 pre-trade risk service operated by the broker-dealer "
            "per 17 CFR § 240.15c3-5(d). Endpoints accept a NewOrder + "
            "PreTradeContext and return the aggregated verdict."
        ),
    )

    class PreTradeCheckRequest(BaseModel):
        bot_id: str
        fleet_id: str = Field(default=fleet_id)
        venue: str
        symbol: str
        side: str
        quantity: Decimal
        order_type: str = "limit"
        limit_price: Decimal | None = None
        equity_usd: Decimal | None = None
        cash_usd: Decimal | None = None
        mark_price: Decimal | None = None

    class PreTradeCheckResponse(BaseModel):
        passed: bool
        severity: str
        block_reasons: list[str]
        citations: list[str]
        verdicts: list[dict[str, str]]

    @app.post("/pretrade/check", response_model=PreTradeCheckResponse)
    async def pretrade_check(req: PreTradeCheckRequest) -> PreTradeCheckResponse:
        from aqp_bots.risk.policies import PreTradeContext
        from aqp_bots.schemas.trading import NewOrder, Side, TimeInForce

        try:
            order = NewOrder(
                venue=req.venue,
                symbol=req.symbol,
                side=Side(req.side),
                quantity=req.quantity,
                order_type=req.order_type,
                time_in_force=TimeInForce.GTC,
                limit_price=req.limit_price,
                client_order_id="risk-svc-coid",
                bot_id=req.bot_id,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"invalid order: {exc}") from exc
        ctx = PreTradeContext(
            mark_price=req.mark_price,
            equity_usd=req.equity_usd,
            cash_usd=req.cash_usd,
        )
        engine.bot_id = req.bot_id  # type: ignore[attr-defined]
        engine.fleet_id = req.fleet_id  # type: ignore[attr-defined]
        verdict = engine.evaluate(order, ctx)
        return PreTradeCheckResponse(
            passed=verdict.passed,
            severity=verdict.severity,
            block_reasons=verdict.block_reasons,
            citations=verdict.citations,
            verdicts=[
                {"policy": v.policy, "severity": v.severity, "reason": v.reason, "citation": v.citation}
                for v in verdict.verdicts
            ],
        )

    @app.get("/pretrade/policies")
    async def list_policies() -> dict[str, Any]:
        return {
            "policies": [
                {"name": p.name, "citation": getattr(p, "citation", "")}
                for p in engine.policies  # type: ignore[attr-defined]
            ],
        }

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        return {"status": "ready"}

    return app


# Re-exported names for the package-level public API.
try:
    from pydantic import BaseModel  # noqa: F401

    PreTradeCheckRequest = None  # type: ignore[misc,assignment]
    PreTradeCheckResponse = None  # type: ignore[misc,assignment]
except Exception:  # noqa: BLE001
    PreTradeCheckRequest = None  # type: ignore[assignment]
    PreTradeCheckResponse = None  # type: ignore[assignment]


__all__ = [
    "PreTradeCheckRequest",
    "PreTradeCheckResponse",
    "create_risk_service_app",
]
