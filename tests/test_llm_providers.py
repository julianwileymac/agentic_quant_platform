"""Tests for the multi-provider LLM router."""
from __future__ import annotations

import pytest

from aqp.llm.providers import (
    get_provider,
    list_providers,
    resolve_model,
)
from aqp.llm.tokens import compute_cost, price_for


def test_list_providers_includes_expected_slugs() -> None:
    providers = list_providers()
    for expected in ("openai", "anthropic", "google", "xai", "deepseek", "groq", "openrouter", "ollama"):
        assert expected in providers


def test_get_provider_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_provider("nope-llm")


def test_resolve_model_adds_prefix() -> None:
    openai = get_provider("openai")
    assert resolve_model(openai, "gpt-4o-mini") == "openai/gpt-4o-mini"
    assert resolve_model(openai, "openai/gpt-4o-mini") == "openai/gpt-4o-mini"


def test_resolve_model_falls_back_to_default() -> None:
    ollama = get_provider("ollama")
    resolved = resolve_model(ollama, None, tier="deep")
    assert resolved.startswith("ollama/")


def test_compute_cost_known_model() -> None:
    # gpt-5.4: 0.003 input, 0.012 output per 1K tokens
    cost = compute_cost("openai/gpt-5.4", prompt_tokens=1000, completion_tokens=500)
    assert cost == pytest.approx(0.003 + 0.006, rel=1e-6)


def test_compute_cost_unknown_model_zero() -> None:
    assert compute_cost("ollama/llama3.2", 1000, 1000) == 0.0


def test_price_for_strips_prefix() -> None:
    price_with = price_for("openai/gpt-5.4-mini")
    price_without = price_for("gpt-5.4-mini")
    assert price_with == price_without
    assert price_with.input_usd > 0
