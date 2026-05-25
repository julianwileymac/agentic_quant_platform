"""Regression tests for ``scripts/ci/check_no_direct_redis_publish.py`` (Rule 4)."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_no_direct_redis_publish")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    return module


def _make_py(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_direct_publish_in_app_code_fails(lint_module, tmp_path) -> None:
    body = (
        "import redis\n"
        "\n"
        "client = redis.Redis.from_url('redis://localhost')\n"
        "client.publish('chan', 'msg')\n"
    )
    _make_py(tmp_path, "aqp/tasks/foo.py", body)
    assert lint_module.main([]) == 1


def test_publish_in_progress_module_passes(lint_module, tmp_path) -> None:
    body = (
        "import redis\n"
        "\n"
        "client = redis.Redis.from_url('redis://localhost')\n"
        "client.publish('chan', 'msg')\n"
    )
    _make_py(tmp_path, "aqp/tasks/_progress.py", body)
    assert lint_module.main([]) == 0


def test_publish_in_ws_layer_passes(lint_module, tmp_path) -> None:
    body = (
        "import redis\n"
        "\n"
        "r = redis.Redis()\n"
        "r.publish('updates', 'x')\n"
    )
    _make_py(tmp_path, "aqp/ws/fanout.py", body)
    assert lint_module.main([]) == 0


def test_publish_in_cache_layer_passes(lint_module, tmp_path) -> None:
    body = (
        "import redis\n"
        "\n"
        "r = redis.Redis()\n"
        "r.publish('inval', 'k')\n"
    )
    _make_py(tmp_path, "aqp/cache/broadcast.py", body)
    assert lint_module.main([]) == 0


def test_kafka_publish_does_not_false_positive(lint_module, tmp_path) -> None:
    # No `redis` import — `producer.publish(...)` is an unrelated kafka API.
    body = (
        "from kafka import KafkaProducer\n"
        "producer = KafkaProducer()\n"
        "producer.publish('topic', b'payload')\n"
    )
    _make_py(tmp_path, "aqp/streaming/foo.py", body)
    assert lint_module.main([]) == 0


def test_async_publish_in_app_code_fails(lint_module, tmp_path) -> None:
    body = (
        "import redis.asyncio as aioredis\n"
        "\n"
        "async def go():\n"
        "    r = aioredis.from_url('redis://x')\n"
        "    await r.publish('chan', 'msg')\n"
    )
    _make_py(tmp_path, "aqp/services/notifier.py", body)
    assert lint_module.main([]) == 1
