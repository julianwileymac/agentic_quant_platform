"""Smoke + behavioural tests for the ``/registry`` introspection API.

We exercise the introspection helpers directly (avoiding the FastAPI
TestClient) because the API module imports the full DB stack. The
functions still exercise the real :mod:`aqp.core.registry` so any
breakage in the registry decorators surfaces immediately.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture(scope="module")
def populated_registry() -> None:
    """Force-import every registry-populating module before running."""
    from aqp.api.routes.registry import _ensure_registry_populated

    _ensure_registry_populated()


def test_list_kinds_returns_known_kinds(populated_registry: None) -> None:
    from aqp.api.routes.registry import list_kinds

    kinds = list_kinds()
    assert "kinds" in kinds
    names = {entry["kind"] for entry in kinds["kinds"]}
    # Core kinds must always be populated.
    assert "strategy" in names or "agent" in names
    # Counts must be non-negative ints.
    for entry in kinds["kinds"]:
        assert isinstance(entry["count"], int)
        assert entry["count"] >= 0


def _first_populated_kind() -> str:
    from aqp.core.registry import list_by_kind, list_kinds

    for kind in list_kinds():
        if list_by_kind(kind):
            return kind
    raise pytest.skip("registry has no populated kinds")


def test_list_components_for_populated_kind(populated_registry: None) -> None:
    from aqp.api.routes.registry import list_components

    kind = _first_populated_kind()
    rows = list_components(kind)
    assert isinstance(rows, list)
    assert rows, f"expected at least one component under kind={kind!r}"


def test_judge_kind_lists_llmjudge(populated_registry: None) -> None:
    """LLMJudge must register under ``kind=judge`` after force-import."""
    from aqp.api.routes.registry import list_components

    rows = list_components("judge")
    aliases = {r.alias for r in rows}
    assert "LLMJudge" in aliases


def test_get_component_param_schema_serialisable(populated_registry: None) -> None:
    from aqp.api.routes.registry import get_component, list_components

    kind = _first_populated_kind()
    rows = list_components(kind)
    detail = get_component(kind, rows[0].alias)
    payload = detail.model_dump(mode="json")
    json.dumps(payload)
    for param in payload["params"]:
        assert "name" in param
        assert "type" in param
        assert "required" in param


def test_unknown_alias_raises_404(populated_registry: None) -> None:
    from fastapi import HTTPException

    from aqp.api.routes.registry import get_component

    with pytest.raises(HTTPException) as exc_info:
        get_component("judge", "DoesNotExist__")
    assert exc_info.value.status_code == 404
