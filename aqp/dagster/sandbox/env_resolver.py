"""ContextVar-based environment substitution for sandbox sessions.

When a sandbox session is "active" inside a Celery task or API
handler, any code that reads through :mod:`aqp.config.settings` for
an *outbound endpoint* (Iceberg REST, Alpha Vantage API, Polaris,
etc.) gets a swapped value pointing at the configured staging
mocks. The ContextVar is thread-/coroutine-local so concurrent
sessions don't interfere.

This is **not** a comprehensive secret-isolation layer — secrets
still resolve through :class:`aqp.credentials.CredentialResolver`.
The goal is narrower: prevent a sandbox component from accidentally
hitting a production warehouse / API.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator

_ACTIVE: ContextVar["SandboxEnvResolver | None"] = ContextVar(
    "aqp_sandbox_env_resolver",
    default=None,
)


@dataclass(slots=True)
class SandboxEnvResolver:
    """Per-session env override. Empty overrides = pass-through."""

    session_id: str
    overrides: dict[str, str] = field(default_factory=dict)

    def resolve(self, key: str, fallback: str) -> str:
        """Return ``overrides[key]`` if set, else ``fallback``."""
        return str(self.overrides.get(key, fallback))


@contextmanager
def enter_sandbox_env(resolver: SandboxEnvResolver) -> Iterator[SandboxEnvResolver]:
    """Activate ``resolver`` for the duration of the block."""
    token = _ACTIVE.set(resolver)
    try:
        yield resolver
    finally:
        _ACTIVE.reset(token)


def sandbox_env_active() -> SandboxEnvResolver | None:
    """Return the active sandbox env resolver, or ``None``."""
    return _ACTIVE.get()


def with_sandbox_overrides(
    session_id: str,
    overrides: dict[str, str] | None = None,
) -> SandboxEnvResolver:
    """Default factory: sensible mocks for Iceberg, Polaris, Alpha Vantage."""
    base: dict[str, str] = {
        "iceberg_rest_uri": "",
        "iceberg_warehouse": f"./data/sandbox/{session_id}/iceberg",
        "polaris_base_url": "",
        "alpha_vantage_base_url": "https://example.invalid/sandbox/alphavantage",
        "datahub_gms_url": "",
        "kafka_bootstrap": "",
    }
    if overrides:
        base.update({str(k): str(v) for k, v in overrides.items()})
    return SandboxEnvResolver(session_id=session_id, overrides=base)


__all__ = [
    "SandboxEnvResolver",
    "enter_sandbox_env",
    "sandbox_env_active",
    "with_sandbox_overrides",
]
