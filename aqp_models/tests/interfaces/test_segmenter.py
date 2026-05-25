"""Smoke tests for the Segmenter interface."""
from __future__ import annotations

import numpy as np

from aqp_models.interfaces import Segmenter


class _NativeSegmenter:
    def segment(self, series: np.ndarray) -> list[int]:
        return [int(series.size // 2)]


def test_native_segment_path() -> None:
    arr = np.arange(20, dtype=float)
    boundaries, metadata = Segmenter(model=_NativeSegmenter()).segment(arr)
    assert metadata.extras["strategy"] == "native_segment"
    assert boundaries[0].index == 10


def test_rolling_zscore_fallback_detects_jump() -> None:
    rng = np.random.default_rng(seed=0)
    base = rng.normal(size=200)
    spike = base.copy()
    spike[100:] += 10.0  # large structural shift
    wrapper = Segmenter(model=object(), window=20, threshold=2.0)
    boundaries, metadata = wrapper.segment(spike)
    assert metadata.extras["strategy"] == "rolling_zscore"
    assert len(boundaries) > 0
    indices = {b.index for b in boundaries}
    # The break should fire at or just after the spike start.
    assert any(95 <= idx <= 130 for idx in indices)
