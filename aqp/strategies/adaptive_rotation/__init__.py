"""Adaptive sector / asset rotation — port of FinRL-Trading patterns.

The full reference implementation at
``inspiration/FinRL-Trading-master/src/strategies/adaptive_rotation/``
spans regime detection, group strength, intra-group ranking, and a
portfolio builder. We provide a lean port that keeps the same
contract:

1. :class:`MarketRegimeClassifier` — buckets the market into
   ``risk_on | neutral | risk_off`` from index momentum + volatility.
2. :class:`GICSBucketUniverseSelector` — selects symbols per GICS
   bucket (growth_tech, cyclical, real_assets, defensive).
3. :class:`AdaptiveRotationAlpha` — emits :class:`Signal` rows whose
   per-bucket weight depends on the active regime.

All three are :class:`IUniverseSelectionModel` / :class:`IAlphaModel`
implementations so they slot into the Lean 5-stage framework.
"""
from aqp.strategies.adaptive_rotation.market_regime import MarketRegimeClassifier
from aqp.strategies.adaptive_rotation.gics_buckets import (
    BUCKET_TO_DEFAULT_WEIGHT,
    GICSBucketUniverseSelector,
    SECTOR_TO_BUCKET,
)
from aqp.strategies.adaptive_rotation.rotation_alpha import AdaptiveRotationAlpha

__all__ = [
    "AdaptiveRotationAlpha",
    "BUCKET_TO_DEFAULT_WEIGHT",
    "GICSBucketUniverseSelector",
    "MarketRegimeClassifier",
    "SECTOR_TO_BUCKET",
]
