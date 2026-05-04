"""Tests for the layered config (vbt-pro merge_dicts port + path access)."""
from __future__ import annotations

import pytest

from aqp.config.layered import (
    UNSET,
    AtomicDict,
    atomic_dict,
    flat_merge_dicts,
    get_path,
    merge_dicts,
)


def test_merge_dicts_recurses_into_nested_dicts() -> None:
    base = {"llm": {"provider": "ollama", "deep_model": "nemotron"}}
    override = {"llm": {"deep_model": "gpt-5.5"}}
    result = merge_dicts(base, override)
    assert result == {"llm": {"provider": "ollama", "deep_model": "gpt-5.5"}}


def test_merge_dicts_later_wins_on_leaf_conflict() -> None:
    a = {"k": 1}
    b = {"k": 2}
    c = {"k": 3}
    assert merge_dicts(a, b, c) == {"k": 3}


def test_merge_dicts_atomic_dict_replaces_subtree() -> None:
    base = {"llm": {"provider": "ollama", "deep_model": "nemotron", "extras": {"x": 1}}}
    override = {"llm": atomic_dict({"provider": "openai"})}
    result = merge_dicts(base, override)
    assert result == {"llm": {"provider": "openai"}}


def test_merge_dicts_unset_sentinel_drops_key() -> None:
    base = {"llm": {"provider": "ollama", "deep_model": "nemotron"}}
    override = {"llm": {"deep_model": UNSET}}
    result = merge_dicts(base, override)
    assert result == {"llm": {"provider": "ollama"}}


def test_merge_dicts_unset_marker_string_drops_key() -> None:
    base = {"llm": {"provider": "ollama", "deep_model": "nemotron"}}
    override = {"llm": {"deep_model": "__unset__"}}
    result = merge_dicts(base, override)
    assert result == {"llm": {"provider": "ollama"}}


def test_flat_merge_dicts_does_not_recurse() -> None:
    base = {"llm": {"provider": "ollama", "deep_model": "nemotron"}}
    override = {"llm": {"provider": "openai"}}
    result = flat_merge_dicts(base, override)
    assert result == {"llm": {"provider": "openai"}}


def test_merge_dicts_returns_fresh_copy() -> None:
    base = {"llm": {"provider": "ollama"}}
    result = merge_dicts(base)
    result["llm"]["provider"] = "openai"
    assert base["llm"]["provider"] == "ollama"


def test_get_path_dotted_access() -> None:
    obj = {"llm": {"providers": {"openai": {"model": "gpt-5.5"}}}}
    assert get_path(obj, "llm.providers.openai.model") == "gpt-5.5"


def test_get_path_returns_default_on_miss() -> None:
    obj = {"llm": {"providers": {}}}
    assert get_path(obj, "llm.providers.openai.model", default="fallback") == "fallback"


def test_get_path_handles_list_index() -> None:
    obj = {"items": [{"name": "a"}, {"name": "b"}]}
    assert get_path(obj, "items[1].name") == "b"


def test_atomic_dict_kwargs_constructor() -> None:
    a = atomic_dict(provider="openai", model="gpt-5.5")
    assert isinstance(a, AtomicDict)
    assert a == {"provider": "openai", "model": "gpt-5.5"}


def test_merge_dicts_preserves_layer_input() -> None:
    base = {"llm": {"deep_model": "nemotron"}}
    override = {"llm": {"deep_model": "gpt-5.5"}}
    merge_dicts(base, override)
    assert base["llm"]["deep_model"] == "nemotron"
    assert override["llm"]["deep_model"] == "gpt-5.5"


def test_merge_dicts_handles_none_layers() -> None:
    base = {"k": 1}
    assert merge_dicts(None, base, None) == {"k": 1}


def test_merge_dicts_six_layer_stack_global_to_project() -> None:
    """Mirror the SCOPE_RESOLUTION_ORDER walk in :func:`resolve_config`."""
    global_layer = {"llm": {"provider": "ollama", "deep_model": "nemotron", "temperature": 0.2}}
    org = {"llm": {"deep_model": "gpt-5.4"}}
    team = {}
    user = {"llm": {"temperature": 0.1}}
    workspace = {"llm": {"deep_model": "gpt-5.5"}}
    project = {"llm": {"temperature": 0.0}}

    effective = merge_dicts(global_layer, org, team, user, workspace, project)
    assert effective == {
        "llm": {
            "provider": "ollama",
            "deep_model": "gpt-5.5",
            "temperature": 0.0,
        }
    }


def test_merge_dicts_rejects_atomic_unset_combo_cleanly() -> None:
    """An AtomicDict followed by UNSET should still drop the key."""
    base = {"llm": atomic_dict(provider="openai")}
    override = {"llm": UNSET}
    result = merge_dicts(base, override)
    assert "llm" not in result
