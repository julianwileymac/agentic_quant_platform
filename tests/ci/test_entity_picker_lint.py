"""Regression tests for ``scripts/ci/check_entity_picker.py``."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_entity_picker")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    monkeypatch.setattr(module, "SCAN_ROOTS", ("aqp_client/src",), raising=True)
    return module


def _make_tsx(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_freetext_urn_input_fails(lint_module, tmp_path) -> None:
    body = (
        "export function Foo() {\n"
        "  return <Input placeholder=\"urn:aqp:dataset:prod:foo.bar\" />;\n"
        "}\n"
    )
    _make_tsx(tmp_path, "aqp_client/src/routes/foo.tsx", body)
    assert lint_module.main([]) == 1


def test_freetext_workspace_id_input_fails(lint_module, tmp_path) -> None:
    body = (
        "export function Bar() {\n"
        "  return <input name=\"workspace_id\" />;\n"
        "}\n"
    )
    _make_tsx(tmp_path, "aqp_client/src/routes/bar.tsx", body)
    assert lint_module.main([]) == 1


def test_select_with_entity_type_fails(lint_module, tmp_path) -> None:
    body = (
        "export function Pick() {\n"
        "  return <select aria-label=\"entity_type\"><option /></select>;\n"
        "}\n"
    )
    _make_tsx(tmp_path, "aqp_client/src/routes/pick.tsx", body)
    assert lint_module.main([]) == 1


def test_entity_picker_self_is_exempt(lint_module, tmp_path) -> None:
    body = (
        "export function EntityPicker() {\n"
        "  return <input placeholder=\"urn:aqp:dataset\" />;\n"
        "}\n"
    )
    _make_tsx(tmp_path, "aqp_client/src/components/common/EntityPicker.tsx", body)
    assert lint_module.main([]) == 0


def test_clean_input_passes(lint_module, tmp_path) -> None:
    body = (
        "export function Search() {\n"
        "  return <Input placeholder=\"Search URN substring\" />;\n"
        "}\n"
    )
    _make_tsx(tmp_path, "aqp_client/src/routes/search.tsx", body)
    assert lint_module.main([]) == 0
