"""Regression tests for ``scripts/ci/check_mcp_audience.py`` (Rule 49)."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_mcp_audience")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    return module


def _make_py(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_mcp_router_without_validator_fails(lint_module, tmp_path) -> None:
    body = (
        "from fastapi import APIRouter\n"
        "\n"
        "router = APIRouter(prefix='/mcp/foo', tags=['foo-mcp'])\n"
        "\n"
        "@router.post('/tools/{name}/invoke')\n"
        "def invoke(name: str): return {'ok': True}\n"
    )
    _make_py(tmp_path, "aqp/foo/mcp/server.py", body)
    assert lint_module.main([]) == 1


def test_mcp_router_with_validator_passes(lint_module, tmp_path) -> None:
    body = (
        "from fastapi import APIRouter, Request\n"
        "from aqp.api.mcp_audience import validate_mcp_audience\n"
        "\n"
        "router = APIRouter(prefix='/mcp/foo', tags=['foo-mcp'])\n"
        "\n"
        "@router.post('/tools/{name}/invoke')\n"
        "def invoke(name: str, request: Request):\n"
        "    validate_mcp_audience(request, 'https://api/foo', mode='strict')\n"
        "    return {'ok': True}\n"
    )
    _make_py(tmp_path, "aqp/foo/mcp/server.py", body)
    assert lint_module.main([]) == 0


def test_non_mcp_router_passes(lint_module, tmp_path) -> None:
    body = (
        "from fastapi import APIRouter\n"
        "\n"
        "router = APIRouter(prefix='/api/v1/data', tags=['data'])\n"
        "\n"
        "@router.get('/health')\n"
        "def health(): return {'ok': True}\n"
    )
    _make_py(tmp_path, "aqp/api/routes/data.py", body)
    assert lint_module.main([]) == 0


def test_mcp_router_imports_validator_but_never_calls_fails(lint_module, tmp_path) -> None:
    body = (
        "from fastapi import APIRouter\n"
        "from aqp.api.mcp_audience import validate_mcp_audience  # noqa: F401\n"
        "\n"
        "router = APIRouter(prefix='/mcp/bar')\n"
        "\n"
        "@router.post('/x')\n"
        "def x(): return {}\n"
    )
    _make_py(tmp_path, "aqp/bar/mcp/server.py", body)
    assert lint_module.main([]) == 1
