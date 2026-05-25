"""Adapter metaclass + registry tests.

The HuggingFace + TorchHub adapters self-register through
``RegistryAdapterMeta`` so we test the registry contract here rather
than calling the actual ``pull`` methods (which require optional deps
+ network).
"""
from __future__ import annotations

import pytest

from aqp_models.adapters import get_adapter, list_adapters


def test_huggingface_and_torchhub_are_registered() -> None:
    descriptors = list_adapters()
    kinds = {d["adapter_kind"] for d in descriptors}
    assert "huggingface" in kinds
    assert "torchhub" in kinds


def test_get_adapter_returns_instance() -> None:
    hf = get_adapter("huggingface")
    assert hf.adapter_kind == "huggingface"
    th = get_adapter("torchhub")
    assert th.adapter_kind == "torchhub"


def test_unknown_adapter_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter("nonexistent")


def test_torchhub_allowlist_resolves_with_defaults() -> None:
    from aqp_models.adapters.torchhub_adapter import DEFAULT_ALLOWLIST, TorchHubAdapter

    adapter = TorchHubAdapter()
    resolved = adapter._resolve_allowlist()  # noqa: SLF001 — exercising internal
    # The default allow-list should at minimum carry the resnet bundle.
    assert "pytorch/vision/resnet50" in resolved
    assert set(DEFAULT_ALLOWLIST).issubset(resolved)


def test_torchhub_pull_rejects_unlisted_model() -> None:
    from aqp_models.adapters import get_adapter

    adapter = get_adapter("torchhub")
    result = adapter.pull("evil/owner/payload")
    assert result.ok is False
    assert "allow-list" in (result.error or "")
