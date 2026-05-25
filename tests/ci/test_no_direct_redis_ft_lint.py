"""Regression tests for ``scripts/ci/check_no_direct_redis_ft.py`` (Rule 11)."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_no_direct_redis_ft")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    return module


def _make_py(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_redis_ft_call_outside_rag_fails(lint_module, tmp_path) -> None:
    body = (
        "import redis\n"
        "\n"
        "client = redis.Redis()\n"
        "results = client.ft('idx').search('q')\n"
    )
    _make_py(tmp_path, "aqp/api/routes/search.py", body)
    assert lint_module.main([]) == 1


def test_redis_ft_in_rag_layer_passes(lint_module, tmp_path) -> None:
    body = (
        "import redis\n"
        "\n"
        "client = redis.Redis()\n"
        "results = client.ft('idx').search('q')\n"
    )
    _make_py(tmp_path, "aqp/rag/hierarchy.py", body)
    assert lint_module.main([]) == 0


def test_no_redis_import_does_not_false_positive(lint_module, tmp_path) -> None:
    # `obj.ft()` on a non-redis object should not fire.
    body = (
        "class Container:\n"
        "    def ft(self): return 42\n"
        "Container().ft()\n"
    )
    _make_py(tmp_path, "aqp/services/x.py", body)
    assert lint_module.main([]) == 0


def test_async_redis_ft_outside_rag_fails(lint_module, tmp_path) -> None:
    body = (
        "import redis.asyncio as aioredis\n"
        "\n"
        "async def go():\n"
        "    r = aioredis.from_url('redis://x')\n"
        "    await r.ft('idx').search('q')\n"
    )
    _make_py(tmp_path, "aqp/agents/searcher.py", body)
    assert lint_module.main([]) == 1
