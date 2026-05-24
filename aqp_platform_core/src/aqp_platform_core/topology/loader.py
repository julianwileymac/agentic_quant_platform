"""Path-driven loader for ``aqp_platform/configs/deployment/topology.yaml``.

The loader is path-only — it intentionally avoids importing
:mod:`aqp.config.settings` so :mod:`aqp_control_plane` can read the
same topology YAML without violating the
``aqp_control_plane -> aqp_platform_core`` boundary (ADR 005).

Resolution order:

1. Explicit ``path`` argument.
2. ``AQP_DEPLOYMENT_TOPOLOGY_PATH`` environment variable.
3. ``aqp_platform/configs/deployment/topology.yaml`` relative to ``cwd``.

Failures raise :class:`TopologyLoadError` with the resolved path and
the underlying YAML/validation error so the control-plane readyz
probe can surface a structured failure instead of a generic 500.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import yaml

from aqp_platform_core.topology.models import DeploymentTopology

_DEFAULT_RELATIVE_PATH = "aqp_platform/configs/deployment/topology.yaml"
_ENV_VAR = "AQP_DEPLOYMENT_TOPOLOGY_PATH"

_LOCK = threading.RLock()
_CACHE: dict[str, DeploymentTopology] = {}


class TopologyLoadError(RuntimeError):
    """Raised when the topology YAML can't be located or validated."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.path = path


def resolve_topology_path(path: str | Path | None = None) -> Path:
    """Resolve the topology YAML path using the documented order."""
    candidate: str | Path | None = path
    if candidate is None:
        candidate = os.environ.get(_ENV_VAR) or _DEFAULT_RELATIVE_PATH
    resolved = Path(candidate).expanduser()
    if not resolved.is_absolute():
        resolved = (Path.cwd() / resolved).resolve()
    return resolved


def load_topology(path: str | Path | None = None) -> DeploymentTopology:
    """Load + validate the topology YAML, with a per-path cache."""
    resolved = resolve_topology_path(path)
    key = str(resolved)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            return cached
        try:
            with resolved.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
        except FileNotFoundError as exc:
            raise TopologyLoadError(
                f"topology YAML not found at {resolved}", path=str(resolved)
            ) from exc
        except yaml.YAMLError as exc:
            raise TopologyLoadError(
                f"topology YAML at {resolved} is not valid YAML: {exc}",
                path=str(resolved),
            ) from exc
        try:
            topology = DeploymentTopology.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            raise TopologyLoadError(
                f"topology YAML at {resolved} failed validation: {exc}",
                path=str(resolved),
            ) from exc
        _CACHE[key] = topology
        return topology


def reload_topology(path: str | Path | None = None) -> DeploymentTopology:
    """Drop the cache for ``path`` and reload from disk."""
    resolved = resolve_topology_path(path)
    with _LOCK:
        _CACHE.pop(str(resolved), None)
    return load_topology(path)


def reset_topology_cache() -> None:
    """Drop every cached topology entry. Test helper."""
    with _LOCK:
        _CACHE.clear()


__all__ = [
    "TopologyLoadError",
    "load_topology",
    "reload_topology",
    "reset_topology_cache",
    "resolve_topology_path",
]
