"""SDK proxy auto-injection tests."""
from __future__ import annotations

import os

import pytest

from aqp_kernels.sdk_proxy import (
    _KERNEL_RUNTIME_INSTALLED,
    install_kernel_runtime,
    is_kernel_runtime,
)


@pytest.fixture(autouse=True)
def _reset_install_flag():
    import aqp_kernels.sdk_proxy as sp

    sp._KERNEL_RUNTIME_INSTALLED = False
    yield
    sp._KERNEL_RUNTIME_INSTALLED = False
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "AQP_KERNEL_ID"):
        os.environ.pop(var, None)


def test_install_is_idempotent():
    assert install_kernel_runtime(rl_proxy_url="http://localhost:8080") is True
    assert install_kernel_runtime(rl_proxy_url="http://localhost:8080") is False


def test_install_sets_https_proxy_env():
    install_kernel_runtime(rl_proxy_url="http://rl-proxy.aqp-system:8080")
    assert os.environ["HTTPS_PROXY"] == "http://rl-proxy.aqp-system:8080"
    assert os.environ["HTTP_PROXY"] == "http://rl-proxy.aqp-system:8080"


def test_install_writes_user_id_when_provided():
    install_kernel_runtime(
        rl_proxy_url="http://localhost:8080",
        user_id="alice@aqp.local",
    )
    assert os.environ.get("AQP_USER_ID") == "alice@aqp.local"


def test_is_kernel_runtime_false_by_default():
    os.environ.pop("AQP_KERNEL_ID", None)
    assert is_kernel_runtime() is False


def test_is_kernel_runtime_true_when_env_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AQP_KERNEL_ID", "krn_test")
    assert is_kernel_runtime() is True
