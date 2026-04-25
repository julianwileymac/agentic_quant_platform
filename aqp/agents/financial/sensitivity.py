"""Lightweight DCF + sensitivity helpers (no LLM).

Used by :class:`EquityReportPipeline` to enrich the
``ValuationOverviewAgent`` prompt with concrete numbers and to render
a sensitivity table in the report payload.
"""
from __future__ import annotations

import math
from typing import Any


def dcf_intrinsic_value(
    *,
    free_cash_flow_t0: float,
    growth_rate: float,
    terminal_growth: float,
    discount_rate: float,
    horizon_years: int = 10,
    shares_outstanding: float | None = None,
    net_debt: float = 0.0,
) -> dict[str, Any]:
    """Return DCF intrinsic value + per-share when ``shares_outstanding`` is set."""
    if discount_rate <= terminal_growth:
        raise ValueError("discount_rate must exceed terminal_growth for DCF to converge")
    pv_explicit = 0.0
    fcf = float(free_cash_flow_t0)
    for t in range(1, int(horizon_years) + 1):
        fcf *= 1.0 + growth_rate
        pv_explicit += fcf / ((1.0 + discount_rate) ** t)
    fcf_terminal = fcf * (1.0 + terminal_growth)
    terminal_value = fcf_terminal / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + discount_rate) ** horizon_years)
    enterprise_value = pv_explicit + pv_terminal
    equity_value = enterprise_value - float(net_debt)
    out: dict[str, Any] = {
        "pv_explicit": float(pv_explicit),
        "pv_terminal": float(pv_terminal),
        "enterprise_value": float(enterprise_value),
        "equity_value": float(equity_value),
        "horizon_years": int(horizon_years),
        "growth_rate": float(growth_rate),
        "terminal_growth": float(terminal_growth),
        "discount_rate": float(discount_rate),
    }
    if shares_outstanding and shares_outstanding > 0:
        out["per_share"] = float(equity_value / shares_outstanding)
    return out


def sensitivity_grid(
    *,
    free_cash_flow_t0: float,
    base_growth: float,
    base_discount: float,
    growth_deltas: list[float] | None = None,
    discount_deltas: list[float] | None = None,
    terminal_growth: float = 0.025,
    horizon_years: int = 10,
    shares_outstanding: float | None = None,
    net_debt: float = 0.0,
) -> dict[str, Any]:
    """Return a 2-D sensitivity table indexed by ``(growth, discount)``."""
    growth_deltas = growth_deltas or [-0.02, -0.01, 0.0, 0.01, 0.02]
    discount_deltas = discount_deltas or [-0.01, 0.0, 0.01, 0.02]
    cells: list[dict[str, Any]] = []
    for dg in growth_deltas:
        for dd in discount_deltas:
            growth = base_growth + dg
            discount = base_discount + dd
            try:
                dcf = dcf_intrinsic_value(
                    free_cash_flow_t0=free_cash_flow_t0,
                    growth_rate=growth,
                    terminal_growth=terminal_growth,
                    discount_rate=discount,
                    horizon_years=horizon_years,
                    shares_outstanding=shares_outstanding,
                    net_debt=net_debt,
                )
                value = dcf.get("per_share") or dcf.get("equity_value")
            except ValueError:
                value = None
            if value is not None and (
                math.isnan(float(value)) or math.isinf(float(value))
            ):
                value = None
            cells.append(
                {
                    "growth": round(growth, 4),
                    "discount": round(discount, 4),
                    "value": float(value) if value is not None else None,
                }
            )
    return {
        "base_growth": base_growth,
        "base_discount": base_discount,
        "terminal_growth": terminal_growth,
        "cells": cells,
    }


__all__ = ["dcf_intrinsic_value", "sensitivity_grid"]
