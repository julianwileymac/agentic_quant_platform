"""Futures-curve analysis flows.

Wraps :mod:`aqp.data.futures.curve` so the AnalysisRuntime can:

* stitch a continuous futures series with a chosen roll rule + adjustment
* persist the result to ``aqp_gold_analysis_futures.<flow>``
* preview the result through the lab UI

Only one flow today (``futures.continuous_curve``); the namespace is left
open so Phase 4 stat-arb basis flows can register here too.
"""
from __future__ import annotations

import logging
from datetime import date as dateType
from typing import Any, Literal

from pydantic import Field

from aqp.analysis.base import FlowContext, FlowParams, FlowResult
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


class ContinuousCurveParams(FlowParams):
    """Parameters for ``futures.continuous_curve``."""

    root_symbol: str = Field(
        description="Root symbol of the curve (ES, NQ, CL, ZN, ...).",
    )
    rule: Literal["volume", "date", "open_interest"] = Field(
        default="volume",
        description="Roll-rule strategy.",
    )
    adjustment: Literal["none", "back_adjusted", "ratio"] = Field(
        default="back_adjusted",
        description="Roll-adjustment mode.",
    )
    days_before_expiry: int = Field(
        default=5,
        ge=0,
        le=30,
        description="Used only when rule == 'date'.",
    )
    min_volume_ratio: float = Field(
        default=1.0,
        ge=0.0,
        description="Used only when rule == 'volume' (or as OI ratio when rule == 'open_interest').",
    )
    start_date: dateType | None = Field(default=None)
    end_date: dateType | None = Field(default=None)
    preview_rows: int = Field(
        default=500,
        ge=10,
        le=5000,
        description="Cap on the per-call row preview returned to the lab.",
    )


@register_analysis_flow(
    name="futures.continuous_curve",
    namespace="futures",
    label="Continuous futures curve (roll-stitched)",
    description=(
        "Build a roll-stitched continuous futures series with the chosen "
        "roll rule (volume / date / open_interest) and adjustment mode "
        "(back_adjusted / ratio / none). Returns the per-day stitched "
        "rows and a list of roll events; the Arrow table is persisted "
        "to aqp_gold_analysis_futures.continuous_curve so subsequent "
        "lookups skip the on-demand stitching cost."
    ),
    params_model=ContinuousCurveParams,
    requires_dataset=False,
    tags=("futures", "curve", "stitch"),
)
def continuous_curve_flow(
    df: Any, params: ContinuousCurveParams, ctx: FlowContext
) -> FlowResult:
    """Build and persist a roll-stitched continuous futures series."""
    from aqp.data.futures.curve import (
        DateBasedRoll,
        OpenInterestRoll,
        VolumeBasedRoll,
        load_curve_snapshots,
        stitch_curve,
        stitched_to_arrow,
    )

    curve = load_curve_snapshots(
        params.root_symbol,
        start_date=params.start_date,
        end_date=params.end_date,
    )
    if not curve.snapshots:
        return FlowResult(
            flow="futures.continuous_curve",
            metrics={"snapshot_count": 0},
            rows=[],
        )

    if params.rule == "volume":
        rule = VolumeBasedRoll(min_volume_ratio=float(params.min_volume_ratio))
    elif params.rule == "date":
        rule = DateBasedRoll(days_before_expiry=int(params.days_before_expiry))
    else:
        rule = OpenInterestRoll(min_oi_ratio=float(params.min_volume_ratio))

    rows, rolls = stitch_curve(curve, rule=rule, adjustment=params.adjustment)  # type: ignore[arg-type]
    preview = [
        {
            "snapshot_date": r.snapshot_date.isoformat(),
            "price": r.price,
            "raw_price": r.raw_price,
            "contract_symbol": r.contract_symbol,
            "contract_expiry": r.contract_expiry.isoformat(),
            "adjustment_factor": r.adjustment_factor,
            "rolled": bool(r.rolled),
        }
        for r in rows[-int(params.preview_rows) :]
    ]
    arrow_table = stitched_to_arrow(
        rows,
        root_symbol=params.root_symbol,
        rule_name=params.rule,
        adjustment=params.adjustment,
    )

    chart: dict[str, Any] = {
        "data": [
            {
                "type": "scatter",
                "mode": "lines",
                "x": [r["snapshot_date"] for r in preview],
                "y": [r["price"] for r in preview],
                "name": f"{params.root_symbol} ({params.adjustment})",
            },
            {
                "type": "scatter",
                "mode": "markers",
                "x": [r["snapshot_date"] for r in preview if r["rolled"]],
                "y": [r["price"] for r in preview if r["rolled"]],
                "name": "rolls",
                "marker": {"size": 8, "symbol": "triangle-up"},
            },
        ],
        "layout": {
            "title": f"{params.root_symbol} continuous curve ({params.rule}/{params.adjustment})",
            "xaxis": {"title": "Date"},
            "yaxis": {"title": "Price"},
        },
    }

    return FlowResult(
        flow="futures.continuous_curve",
        metrics={
            "snapshot_count": len(curve.snapshots),
            "stitched_row_count": len(rows),
            "roll_count": len(rolls),
            "rule": params.rule,
            "adjustment": params.adjustment,
            "contract_universe_size": len(curve.contract_universe),
        },
        rows=preview,
        arrow_table=arrow_table,
        artifacts={
            "rolls": [
                {
                    "snapshot_date": e.snapshot_date.isoformat(),
                    "from_contract": e.from_contract,
                    "from_expiry": e.from_expiry.isoformat(),
                    "to_contract": e.to_contract,
                    "to_expiry": e.to_expiry.isoformat(),
                    "rule_name": e.rule_name,
                    "from_price": e.from_price,
                    "to_price": e.to_price,
                }
                for e in rolls
            ]
        },
        chart=chart,
    )
