"""Validate / YAML emit / Fetcher stub generation tests."""
from __future__ import annotations

import ast

import pytest

from aqp.data.airbyte.builder import (
    state_to_fetcher_stub,
    state_to_yaml,
    validate_manifest,
)


def _valid_state() -> dict:
    return {
        "metadata": {
            "connector_id": "demo_quotes",
            "display_name": "Demo Quotes",
            "docs_url": "https://example.com/docs",
        },
        "auth": {
            "auth_kind": "bearer",
            "credential_ref": "demo/default/token",
        },
        "requester": {
            "base_url": "https://api.example.com",
            "method": "GET",
            "default_headers": {"X-API-Version": "v2"},
            "default_params": {},
            "timeout_s": 30,
        },
        "paginator": {"paginator_kind": "page_increment", "page_size": 100, "page_param": "page"},
        "extractor": {"record_path": "data.results"},
        "streams": [{"name": "quotes", "path": "/v1/quotes", "primary_key": "id"}],
    }


def test_validate_passes_for_complete_state() -> None:
    report = validate_manifest(_valid_state())
    assert report["errors"] == []


def test_validate_requires_connector_id() -> None:
    state = _valid_state()
    state["metadata"]["connector_id"] = ""
    report = validate_manifest(state)
    assert any("connector_id" in err for err in report["errors"])


def test_validate_requires_credential_ref_when_auth_set() -> None:
    state = _valid_state()
    state["auth"]["credential_ref"] = ""
    report = validate_manifest(state)
    assert any("credential_ref" in err for err in report["errors"])


def test_yaml_round_trip_contains_stream() -> None:
    yaml_text = state_to_yaml(_valid_state())
    assert "quotes" in yaml_text
    assert "DeclarativeStream" in yaml_text
    assert "BearerAuthenticator" in yaml_text


def test_yaml_raises_on_invalid_state() -> None:
    state = _valid_state()
    state["streams"] = []
    with pytest.raises(ValueError):
        state_to_yaml(state)


def test_fetcher_stub_compiles() -> None:
    rendered = state_to_fetcher_stub(_valid_state())
    # The stub must parse as valid Python.
    tree = ast.parse(rendered)
    # And it must define a class ending in 'Fetcher'.
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assert any(name.endswith("Fetcher") for name in classes)
    # And the decorator must be `register_source_fetcher`.
    assert "register_source_fetcher" in rendered
    # And credentials must resolve through CredentialResolver, not env reads.
    assert "get_resolver()" in rendered
    assert "settings." not in rendered
