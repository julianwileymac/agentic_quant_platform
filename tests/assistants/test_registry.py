"""Assistant registry — code-driven + YAML-driven loading + replay."""
from __future__ import annotations

from pathlib import Path

import pytest

from aqp.assistants.registry import (
    add_assistant_spec,
    clear_assistant_registry,
    get_assistant_spec,
    list_assistant_specs,
    persist_spec,
    reload_yaml_dir,
)
from aqp.assistants.spec import AssistantSpec


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    clear_assistant_registry()


def test_add_and_get_spec_roundtrip():
    spec = AssistantSpec(
        name="t.platform",
        mode="agent",
        agent_spec_name="codebase_assistant",
    )
    add_assistant_spec(spec)
    again = get_assistant_spec("t.platform")
    assert again.snapshot_hash() == spec.snapshot_hash()


def test_get_assistant_spec_raises_for_unknown():
    with pytest.raises(KeyError):
        get_assistant_spec("does.not.exist")


def test_reload_yaml_dir_loads_specs(tmp_path: Path) -> None:
    yaml_path = tmp_path / "demo.yaml"
    yaml_path.write_text(
        "name: demo\n"
        "mode: agent\n"
        "agent_spec_name: codebase_assistant\n"
        "description: demo spec\n",
        encoding="utf-8",
    )
    n = reload_yaml_dir(tmp_path)
    assert n == 1
    assert get_assistant_spec("demo").description == "demo spec"


def test_persist_spec_noops_when_versioning_disabled(monkeypatch):
    """Without the flag the registry stays in-memory."""
    from aqp.config import settings

    monkeypatch.setattr(settings, "assistant_engine_versioning_enabled", False)
    spec = AssistantSpec(
        name="t.persist",
        mode="agent",
        agent_spec_name="codebase_assistant",
    )
    add_assistant_spec(spec)
    assert persist_spec(spec) is None


def test_list_assistant_specs_returns_registered():
    spec = AssistantSpec(
        name="t.listed",
        mode="agent",
        agent_spec_name="codebase_assistant",
    )
    add_assistant_spec(spec)
    names = [s.name for s in list_assistant_specs()]
    assert "t.listed" in names
