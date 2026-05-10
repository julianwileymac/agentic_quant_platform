"""Load + simulate-execute Dagster components inside a sandbox session.

The executor is intentionally **defensive**: when the Dagster
sandbox utilities (:func:`dagster.components.testing.create_defs_folder_sandbox`)
are available, we use them. When they aren't (e.g. local dev with a
slim Dagster install), we fall back to a manifest-only walk that
parses the component YAML and emits synthetic events so the UI can
still iterate on the form state.

This trade-off keeps the sandbox usable across heterogeneous
deployments (the rpi cluster runs the full Dagster code server,
while a developer laptop may not).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SandboxEvent:
    """One streamed event from a sandbox execution."""

    stage: str
    message: str
    timestamp: float = 0.0
    asset_key: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "message": self.message,
            "timestamp": self.timestamp or time.time(),
            "asset_key": list(self.asset_key),
            "metadata": dict(self.metadata),
        }


class SandboxExecutor:
    """Load + execute Dagster components from a sandbox folder."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._defs: Any | None = None
        self._asset_keys: list[list[str]] = []

    # ----------------------------------------------------------- loading
    def load(self) -> dict[str, Any]:
        try:
            from dagster.components.testing import (  # type: ignore[import-not-found]
                create_defs_folder_sandbox,
            )

            with create_defs_folder_sandbox(folder=self.folder) as sandbox:
                # Defer to Dagster's actual sandbox; record asset keys.
                defs = sandbox.load_component_and_build_defs()
                asset_nodes = list(getattr(defs, "asset_graph", []) or [])
                self._asset_keys = [list(getattr(node, "key", [])) for node in asset_nodes]
                self._defs = defs
            return {
                "ok": True,
                "asset_keys": self._asset_keys,
                "loader": "dagster.components.testing",
            }
        except Exception as exc:  # noqa: BLE001
            logger.info("dagster sandbox unavailable; falling back to manifest walk: %s", exc)
        return self._fallback_load()

    def _fallback_load(self) -> dict[str, Any]:
        """Parse ``*.yaml`` files in the sandbox folder to derive asset keys."""
        keys: list[list[str]] = []
        if not self.folder.exists():
            return {"ok": False, "error": "sandbox folder does not exist", "asset_keys": []}
        for path in sorted(self.folder.glob("*.yaml")):
            stem = path.stem
            keys.append(["sandbox", stem])
        self._asset_keys = keys
        return {
            "ok": True,
            "asset_keys": keys,
            "loader": "fallback",
        }

    # ----------------------------------------------------------- execution
    def stream_execute(self) -> Iterable[SandboxEvent]:
        """Yield :class:`SandboxEvent` records describing the simulated run."""
        if self._defs is None:
            self.load()
        yield SandboxEvent(stage="start", message="Sandbox session begin", timestamp=time.time())
        for key in self._asset_keys:
            yield SandboxEvent(
                stage="materialize",
                message=f"materialising {'/'.join(key)}",
                timestamp=time.time(),
                asset_key=key,
                metadata={"sandbox": True},
            )
        yield SandboxEvent(
            stage="done",
            message=f"executed {len(self._asset_keys)} sandbox asset(s)",
            timestamp=time.time(),
            metadata={"asset_count": len(self._asset_keys)},
        )


__all__ = ["SandboxEvent", "SandboxExecutor"]
