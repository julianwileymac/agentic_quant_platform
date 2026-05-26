"""Bedrock LLM provider registration smoke test (Phase D of AWS hybrid).

Confirms:

1. ``bedrock`` is in ``PROVIDERS`` with the expected ``litellm_prefix``.
2. ``_bedrock_extra_kwargs`` injects ``aws_region_name`` from the
   settings chain.
3. ``_bedrock_extra_kwargs`` emits ``guardrailConfig`` only when the
   matching Settings field is set.
4. ``router_complete`` passes the extras to LiteLLM verbatim (asserts
   via monkey-patched ``litellm.completion``).
"""
from __future__ import annotations

from unittest import mock

import pytest


def test_bedrock_provider_in_catalog():
    from aqp.llm.providers.catalog import PROVIDERS

    assert "bedrock" in PROVIDERS
    spec = PROVIDERS["bedrock"]
    assert spec.litellm_prefix == "bedrock/"
    assert spec.requires_api_key is False
    assert "claude-sonnet-4-5" in spec.default_deep_model


def test_bedrock_extra_kwargs_uses_region_fallbacks(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    from aqp.llm.providers import router as router_mod

    monkeypatch.setattr(
        router_mod.settings,
        "bedrock_region",
        "",
        raising=False,
    )
    monkeypatch.setattr(
        router_mod.settings,
        "aws_region",
        "ap-southeast-2",
        raising=False,
    )
    extras = router_mod._bedrock_extra_kwargs()
    assert extras["aws_region_name"] == "ap-southeast-2"
    assert "guardrailConfig" not in extras


def test_bedrock_extra_kwargs_emits_guardrail(monkeypatch):
    from aqp.llm.providers import router as router_mod

    monkeypatch.setattr(router_mod.settings, "bedrock_region", "us-east-1", raising=False)
    monkeypatch.setattr(
        router_mod.settings,
        "bedrock_guardrail_id",
        "gr-12345",
        raising=False,
    )
    monkeypatch.setattr(
        router_mod.settings,
        "bedrock_guardrail_version",
        "1",
        raising=False,
    )
    extras = router_mod._bedrock_extra_kwargs()
    assert extras["aws_region_name"] == "us-east-1"
    gc = extras["guardrailConfig"]
    assert gc["guardrailIdentifier"] == "gr-12345"
    assert gc["guardrailVersion"] == "1"
    assert gc["trace"] == "enabled"


def test_router_complete_passes_bedrock_extras_to_litellm(monkeypatch):
    """The ``bedrock`` provider must inject ``aws_region_name`` on every call."""
    fake_completion = mock.MagicMock(
        return_value={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )

    fake_litellm = mock.MagicMock()
    fake_litellm.completion = fake_completion
    fake_litellm.drop_params = False

    monkeypatch.setitem(__import__("sys").modules, "litellm", fake_litellm)

    from aqp.llm.providers import router as router_mod

    monkeypatch.setattr(router_mod.settings, "bedrock_region", "us-east-1", raising=False)
    monkeypatch.setattr(router_mod.settings, "bedrock_guardrail_id", "", raising=False)

    router_mod.router_complete(
        provider="bedrock",
        model="anthropic.claude-haiku-4-5-20251022-v1:0",
        prompt="ping",
    )

    assert fake_completion.called
    call_kwargs = fake_completion.call_args.kwargs
    assert call_kwargs["aws_region_name"] == "us-east-1"
    # The bedrock path MUST NOT inject an api_key (SCP-denied keys).
    assert "api_key" not in call_kwargs
