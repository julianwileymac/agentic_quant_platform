"""Strategy ports from inspiration/notebooks-master.

Academic systematic strategies originally built on the proprietary
``vivace`` library. We re-implement signal math against AQP bars.
See ``extractions/notebooks/REFERENCE.md``.
"""
from __future__ import annotations

from aqp.strategies.notebooks.alphas import (
    BaltasTrendAlpha,
    BreakoutTrendAlpha,
    ChineseFuturesTrendAlpha,
    CommodityBasisMomentumAlpha,
    CommodityBasisReversalAlpha,
    CommodityIntraCurveAlpha,
    CommodityMomentumAlpha,
    CommoditySkewnessAlpha,
    CommodityTermStructureAlpha,
    ConnorsDoubleSevensStrategy,
    ConnorsMonthEndStrategy,
    ConnorsTenDayLowsStrategy,
    ConnorsThreeDownStrategy,
    CrackSpreadStatArbStrategy,
    CrossAssetSkewnessAlpha,
    CrushSpreadStatArbStrategy,
    FXCarryAlpha,
    GaoIntradayMomentumStrategy,
    MoskowitzTSMOMAlpha,
    OvernightReturnsAlpha,
)


__all__ = [
    "BaltasTrendAlpha",
    "BreakoutTrendAlpha",
    "ChineseFuturesTrendAlpha",
    "CommodityBasisMomentumAlpha",
    "CommodityBasisReversalAlpha",
    "CommodityIntraCurveAlpha",
    "CommodityMomentumAlpha",
    "CommoditySkewnessAlpha",
    "CommodityTermStructureAlpha",
    "ConnorsDoubleSevensStrategy",
    "ConnorsMonthEndStrategy",
    "ConnorsTenDayLowsStrategy",
    "ConnorsThreeDownStrategy",
    "CrackSpreadStatArbStrategy",
    "CrossAssetSkewnessAlpha",
    "CrushSpreadStatArbStrategy",
    "FXCarryAlpha",
    "GaoIntradayMomentumStrategy",
    "MoskowitzTSMOMAlpha",
    "OvernightReturnsAlpha",
]
