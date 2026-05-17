from __future__ import annotations

from aqp.data.engine.registry import get_node_class
from aqp.data.fabric.schema_registry import OHLCVSchema
from aqp.data.fetchers.api.akshare_ohlcv import AkshareOHLCVFetcher


def test_akshare_ohlcv_class_attrs() -> None:
    assert AkshareOHLCVFetcher.CANONICAL_SCHEMA_CLASS is OHLCVSchema
    assert AkshareOHLCVFetcher.PROVIDER_NAME == "AKShare"
    assert AkshareOHLCVFetcher.LOADER_SCHEMA_METADATA["requires_auth"] is False


def test_akshare_ohlcv_registered() -> None:
    assert get_node_class("source.akshare_ohlcv") is AkshareOHLCVFetcher
