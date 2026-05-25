"""Regression tests for ``scripts/ci/check_step_up_mfa.py`` (Rule 52)."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_step_up_mfa")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    return module


def _make_py(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_kill_switch_without_step_up_fails(lint_module, tmp_path) -> None:
    body = (
        "from fastapi import APIRouter\n"
        "\n"
        "router = APIRouter(prefix='/portfolio')\n"
        "\n"
        "@router.post('/kill_switch')\n"
        "def kill_switch(): return {'ok': True}\n"
    )
    _make_py(tmp_path, "aqp/api/routes/portfolio.py", body)
    assert lint_module.main([]) == 1


def test_kill_switch_with_dependencies_step_up_passes(lint_module, tmp_path) -> None:
    body = (
        "from fastapi import APIRouter, Depends\n"
        "from aqp.api.security_stepup import require_step_up\n"
        "\n"
        "router = APIRouter(prefix='/portfolio')\n"
        "\n"
        "@router.post(\n"
        "    '/kill_switch',\n"
        "    dependencies=[Depends(require_step_up(max_age_seconds=120))],\n"
        ")\n"
        "def kill_switch(): return {'ok': True}\n"
    )
    _make_py(tmp_path, "aqp/api/routes/portfolio.py", body)
    assert lint_module.main([]) == 0


def test_halt_with_function_param_step_up_passes(lint_module, tmp_path) -> None:
    body = (
        "from fastapi import APIRouter, Depends\n"
        "from aqp.api.security_stepup import require_step_up\n"
        "\n"
        "router = APIRouter(prefix='/agents')\n"
        "\n"
        "@router.post('/halt')\n"
        "def halt(_: str = Depends(require_step_up(max_age_seconds=180))):\n"
        "    return {'ok': True}\n"
    )
    _make_py(tmp_path, "aqp/api/routes/agents.py", body)
    assert lint_module.main([]) == 0


def test_broker_credential_post_without_step_up_fails(lint_module, tmp_path) -> None:
    body = (
        "from fastapi import APIRouter\n"
        "\n"
        "router = APIRouter(prefix='/api/v1/broker_credentials')\n"
        "\n"
        "@router.post('')\n"
        "def create(): return {}\n"
    )
    _make_py(tmp_path, "aqp/api/routes/broker_credentials.py", body)
    assert lint_module.main([]) == 1


def test_non_destructive_route_passes(lint_module, tmp_path) -> None:
    body = (
        "from fastapi import APIRouter\n"
        "\n"
        "router = APIRouter(prefix='/api/v1/foo')\n"
        "\n"
        "@router.get('/list')\n"
        "def list_foo(): return []\n"
    )
    _make_py(tmp_path, "aqp/api/routes/foo.py", body)
    assert lint_module.main([]) == 0


def test_subproject_shim_underscore_dep_passes(lint_module, tmp_path) -> None:
    # `aqp_ratelimit` ships its own `_require_step_up` shim. The lint
    # accepts it as a synonym to keep the subproject pattern green.
    body = (
        "from fastapi import APIRouter, Depends\n"
        "\n"
        "router = APIRouter(prefix='/api/v1/me/ratelimit')\n"
        "\n"
        "def _require_step_up(): pass\n"
        "\n"
        "@router.post(\n"
        "    '/reserve',\n"
        "    dependencies=[Depends(_require_step_up)],\n"
        ")\n"
        "def reserve(): return {}\n"
    )
    _make_py(tmp_path, "aqp_ratelimit/api/routes/ratelimit.py", body)
    assert lint_module.main([]) == 0
