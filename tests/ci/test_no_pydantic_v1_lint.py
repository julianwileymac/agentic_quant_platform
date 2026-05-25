"""Regression tests for ``scripts/ci/check_no_pydantic_v1.py``."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_no_pydantic_v1")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    monkeypatch.setattr(module, "SCAN_ROOTS", ("aqp",), raising=True)
    return module


def _make_py(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_dict_call_in_pydantic_module_fails(lint_module, tmp_path) -> None:
    body = (
        "from pydantic import BaseModel\n"
        "\n"
        "class Foo(BaseModel):\n"
        "    x: int = 1\n"
        "\n"
        "f = Foo()\n"
        "payload = f.dict()\n"
    )
    _make_py(tmp_path, "aqp/foo.py", body)
    assert lint_module.main([]) == 1


def test_parse_obj_call_fails(lint_module, tmp_path) -> None:
    body = (
        "from pydantic import BaseModel\n"
        "\n"
        "class Foo(BaseModel):\n"
        "    x: int = 1\n"
        "\n"
        "Foo.parse_obj({'x': 2})\n"
    )
    _make_py(tmp_path, "aqp/bar.py", body)
    assert lint_module.main([]) == 1


def test_dict_call_outside_pydantic_module_passes(lint_module, tmp_path) -> None:
    body = (
        "def make():\n"
        "    return {'x': 1}\n"
        "\n"
        "data = make()\n"
        "k = data.keys()\n"
    )
    _make_py(tmp_path, "aqp/baz.py", body)
    # No pydantic import, so the lint won't fire even if there's a `.dict(...)` somewhere.
    assert lint_module.main([]) == 0


def test_v2_methods_pass(lint_module, tmp_path) -> None:
    body = (
        "from pydantic import BaseModel\n"
        "\n"
        "class Foo(BaseModel):\n"
        "    x: int = 1\n"
        "\n"
        "f = Foo()\n"
        "payload = f.model_dump()\n"
        "Foo.model_validate({'x': 2})\n"
    )
    _make_py(tmp_path, "aqp/qux.py", body)
    assert lint_module.main([]) == 0
