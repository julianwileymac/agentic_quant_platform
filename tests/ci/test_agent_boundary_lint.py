"""Regression tests for ``scripts/ci/check_agent_boundary.py``."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_agent_boundary")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    monkeypatch.setattr(module, "SCAN_ROOT", tmp_path / "aqp" / "agents", raising=True)
    return module


def _make_py(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_agent_tool_with_persistence_import_fails(lint_module, tmp_path) -> None:
    body = (
        "from aqp.persistence.db import SessionLocal\n"
        "\n"
        "def run():\n"
        "    with SessionLocal() as session:\n"
        "        return session\n"
    )
    _make_py(tmp_path, "aqp/agents/tools/foo.py", body)
    assert lint_module.main([]) == 1


def test_ledger_writer_exception_passes(lint_module, tmp_path) -> None:
    body = (
        "from aqp.persistence.db import SessionLocal\n"
        "\n"
        "def write_ledger() -> None:\n"
        "    pass\n"
    )
    _make_py(tmp_path, "aqp/agents/runtime.py", body)
    assert lint_module.main([]) == 0


def test_orchestration_runtime_exception_passes(lint_module, tmp_path) -> None:
    body = "import aqp.persistence\n"
    _make_py(tmp_path, "aqp/agents/orchestration/runtime.py", body)
    assert lint_module.main([]) == 0


def test_clean_agent_module_passes(lint_module, tmp_path) -> None:
    body = (
        "from aqp.data.mcp.registry import get_data_mcp_tool\n"
        "\n"
        "def screen():\n"
        "    return get_data_mcp_tool('data.screening.list_candidates')\n"
    )
    _make_py(tmp_path, "aqp/agents/screening/llm_screener.py", body)
    assert lint_module.main([]) == 0


def test_submodule_import_also_flagged(lint_module, tmp_path) -> None:
    body = "from aqp.persistence.models import BacktestRun\n"
    _make_py(tmp_path, "aqp/agents/tools/risk_tool.py", body)
    assert lint_module.main([]) == 1
