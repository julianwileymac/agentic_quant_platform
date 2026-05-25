"""Regression tests for ``scripts/ci/check_no_broker_settings.py`` (Rule 55)."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_no_broker_settings")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    return module


def _make_py(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_alpaca_settings_read_outside_credentials_fails(lint_module, tmp_path) -> None:
    body = (
        "from aqp.config import settings\n"
        "\n"
        "key = settings.alpaca_api_key\n"
        "secret = settings.alpaca_secret_key\n"
    )
    _make_py(tmp_path, "aqp/trading/brokerages/alpaca.py", body)
    assert lint_module.main([]) == 1


def test_ibkr_settings_read_in_credentials_layer_passes(lint_module, tmp_path) -> None:
    body = (
        "from aqp.config import settings\n"
        "\n"
        "host = settings.ibkr_host\n"
        "port = settings.ibkr_port\n"
    )
    _make_py(tmp_path, "aqp/credentials/stores/broker_credential_store.py", body)
    assert lint_module.main([]) == 0


def test_aliased_settings_read_fails(lint_module, tmp_path) -> None:
    body = (
        "from aqp.config import settings as cfg\n"
        "\n"
        "token = cfg.tradier_token\n"
    )
    _make_py(tmp_path, "aqp/services/tradier.py", body)
    assert lint_module.main([]) == 1


def test_broker_credential_store_get_passes(lint_module, tmp_path) -> None:
    # Replacement pattern: workspace-scoped credential lookup.
    body = (
        "from aqp.credentials import BrokerCredentialStore\n"
        "\n"
        "store = BrokerCredentialStore()\n"
        "creds = store.get(workspace_id='w', broker='alpaca')\n"
        "key = creds.api_key\n"
    )
    _make_py(tmp_path, "aqp/trading/brokerages/alpaca.py", body)
    assert lint_module.main([]) == 0


def test_unrelated_settings_read_passes(lint_module, tmp_path) -> None:
    body = (
        "from aqp.config import settings\n"
        "\n"
        "url = settings.redis_url\n"
        "limit = settings.task_limit\n"
    )
    _make_py(tmp_path, "aqp/services/x.py", body)
    assert lint_module.main([]) == 0


def test_polygon_via_get_settings_factory_fails(lint_module, tmp_path) -> None:
    body = (
        "from aqp.config import get_settings\n"
        "\n"
        "cfg = get_settings()\n"
        "key = cfg.polygon_api_key\n"
    )
    _make_py(tmp_path, "aqp/data/polygon.py", body)
    assert lint_module.main([]) == 1
