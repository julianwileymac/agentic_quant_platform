"""Kernel-startup hook: HTTPS_PROXY + requests/httpx monkey-patch.

On kernel boot, set ``HTTPS_PROXY`` env so subsequent ``requests``
and ``httpx`` calls automatically route through the AQP rate-limit
forward proxy. Also monkey-patch the existing imported classes
in case the user already imported them BEFORE the hook ran
(common in saved notebooks).

This is the chokepoint root AGENTS.md rule 26 implementation
calls into: every vendor API call from inside a kernel debits
the user's (user_id, service, key_id) bucket.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


_KERNEL_RUNTIME_INSTALLED = False


def is_kernel_runtime() -> bool:
    """Return True if the current process is running inside an AQP kernel pod."""
    return bool(os.environ.get("AQP_KERNEL_ID"))


def install_kernel_runtime(
    *,
    rl_proxy_url: str | None = None,
    user_id: str | None = None,
) -> bool:
    """Idempotently install the rate-limit proxy hook.

    Returns ``True`` on first successful install, ``False`` on
    subsequent calls (so the kernel startup script can call it
    safely from multiple paths).
    """
    global _KERNEL_RUNTIME_INSTALLED
    if _KERNEL_RUNTIME_INSTALLED:
        return False
    proxy = (
        rl_proxy_url
        or os.environ.get("AQP_RATELIMIT_PROXY_URL")
        or "http://rl-proxy.aqp-system.svc.cluster.local:8080"
    )
    os.environ.setdefault("HTTPS_PROXY", proxy)
    os.environ.setdefault("HTTP_PROXY", proxy)
    os.environ.setdefault(
        "NO_PROXY",
        ".aqp-system.svc,.aqp-data-services.svc,.aqp-elt.svc,127.0.0.1,localhost",
    )
    _patch_requests(proxy)
    _patch_httpx(proxy)
    if user_id:
        os.environ.setdefault("AQP_USER_ID", str(user_id))
    _KERNEL_RUNTIME_INSTALLED = True
    logger.info(
        "aqp-kernels: kernel runtime installed (proxy=%s, user_id=%s)",
        proxy,
        user_id or "<unspecified>",
    )
    return True


def _patch_requests(proxy: str) -> None:
    try:
        import requests
    except ImportError:
        return
    original_init = requests.Session.__init__  # type: ignore[assignment]

    def _patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        self.proxies = {"http": proxy, "https": proxy}
        self.trust_env = True

    requests.Session.__init__ = _patched_init  # type: ignore[method-assign]


def _patch_httpx(proxy: str) -> None:
    try:
        import httpx
    except ImportError:
        return
    original_client_init = httpx.Client.__init__
    original_async_client_init = httpx.AsyncClient.__init__

    def _patched_client_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("proxy", proxy)
        original_client_init(self, *args, **kwargs)

    def _patched_async_client_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("proxy", proxy)
        original_async_client_init(self, *args, **kwargs)

    httpx.Client.__init__ = _patched_client_init  # type: ignore[method-assign]
    httpx.AsyncClient.__init__ = _patched_async_client_init  # type: ignore[method-assign]


__all__ = ["install_kernel_runtime", "is_kernel_runtime"]
