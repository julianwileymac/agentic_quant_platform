"""Regression tests for ``scripts/ci/check_no_hardcoded_svc_urls.py`` (Rule 47)."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def lint_module(load_lint_script, monkeypatch, tmp_path):
    module = load_lint_script("check_no_hardcoded_svc_urls")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path, raising=True)
    return module


def _make(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_hardcoded_svc_url_in_app_code_fails(lint_module, tmp_path) -> None:
    body = "REDIS_URL = 'redis://redis.aqp.svc.cluster.local:6379/0'\n"
    _make(tmp_path, "aqp/services/cache.py", body)
    assert lint_module.main([]) == 1


def test_url_in_topology_service_passes(lint_module, tmp_path) -> None:
    body = "DEFAULT_REDIS = 'redis.aqp.svc.cluster.local'\n"
    _make(tmp_path, "aqp/config/topology_fallback.py", body)
    assert lint_module.main([]) == 0


def test_url_in_deployment_yaml_passes(lint_module, tmp_path) -> None:
    body = "value: redis.aqp.svc.cluster.local\n"
    _make(tmp_path, "aqp_platform/deployments/redis.yaml", body)
    assert lint_module.main([]) == 0


def test_url_in_terraform_passes(lint_module, tmp_path) -> None:
    body = 'resource "x" { url = "api.aqp.svc.cluster.local" }\n'
    _make(tmp_path, "aqp_platform/terraform/main.tf.yaml", body)
    # .tf.yaml ends with .yaml so it matches the text-extension scan,
    # but it's under the exempt prefix.
    assert lint_module.main([]) == 0


def test_no_hardcoded_url_passes(lint_module, tmp_path) -> None:
    body = (
        "from aqp.config.topology_fallback import service_url\n"
        "REDIS_URL = service_url('redis')\n"
    )
    _make(tmp_path, "aqp/services/cache.py", body)
    assert lint_module.main([]) == 0


def test_unrelated_dotted_string_passes(lint_module, tmp_path) -> None:
    # Looks like a hostname but doesn't end in `.svc.cluster.local`.
    body = "API = 'https://api.example.com'\n"
    _make(tmp_path, "aqp/services/x.py", body)
    assert lint_module.main([]) == 0
