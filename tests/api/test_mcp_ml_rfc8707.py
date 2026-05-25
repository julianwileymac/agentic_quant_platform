"""RFC 9728 + RFC 8707 conformance smoke tests for the MLOps MCP server.

The full audience-mismatch + WWW-Authenticate header behaviour is
covered by the parent :file:`tests/mcp/test_no_token_passthrough.py`
linter; this file exercises the well-known metadata route + the
canonical-URI helper specifically for the new ``/mcp/ml`` surface
introduced by the MLOps slice.
"""
from __future__ import annotations

import pytest


def test_canonical_uri_helper_reads_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api import mcp_audience

    monkeypatch.setattr(
        "aqp.config.settings.mcp_ml_canonical_uri",
        "https://api.aqp.fund/mcp/ml",
        raising=False,
    )
    assert mcp_audience.get_ml_mcp_canonical_uri() == "https://api.aqp.fund/mcp/ml"


def test_well_known_router_exposes_ml_metadata_path() -> None:
    from aqp.api.well_known import build_well_known_router

    router = build_well_known_router()
    routes = [r.path for r in router.routes]
    assert "/.well-known/oauth-protected-resource/mcp/ml" in routes


def test_ml_mcp_canonical_uri_appears_in_exported_helpers() -> None:
    """The helper MUST be exported so the ``aqp-ml-mcp`` server can import it."""
    from aqp.api import mcp_audience

    assert "get_ml_mcp_canonical_uri" in mcp_audience.__all__
