"""Embedded Airbyte runner for local connector development and dry-runs."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aqp.config import settings
from aqp.data.airbyte.models import (
    AirbyteEmbeddedReadRequest,
    AirbyteStreamSpec,
)
from aqp.data.airbyte.registry import get_connector

logger = logging.getLogger(__name__)


class EmbeddedAirbyteRunner:
    """Small wrapper around optional PyAirbyte execution.

    The default code path is intentionally dry-run friendly and hermetic:
    it resolves AQP's connector metadata without installing or executing
    connector packages. If PyAirbyte is installed and ``dry_run=False``,
    the runner delegates to its public ``get_source`` surface.
    """

    def __init__(self, cache_root: Path | None = None) -> None:
        self.cache_root = Path(cache_root or settings.airbyte_embedded_cache_dir)

    def spec(self, connector_id: str) -> dict[str, Any]:
        connector = get_connector(connector_id)
        return {
            "connector": connector.model_dump(mode="json"),
            "config_schema": connector.config_schema,
            "capabilities": connector.capabilities,
        }

    def discover(
        self,
        connector_id: str,
        config: dict[str, Any] | None = None,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        connector = get_connector(connector_id)
        if dry_run:
            return _catalog_payload(connector.streams, source="registry")

        source = self._pyairbyte_source(connector_id, config or {})
        catalog = source.discover()
        return {"source": "pyairbyte", "catalog": _jsonable(catalog)}

    def check(
        self,
        connector_id: str,
        config: dict[str, Any] | None = None,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        connector = get_connector(connector_id)
        if dry_run:
            required = [
                key
                for key, schema in (connector.config_schema.get("properties") or {}).items()
                if key in connector.config_schema.get("required", [])
                and not (config or {}).get(key)
            ]
            return {"ok": not required, "missing": required, "mode": "dry_run"}

        source = self._pyairbyte_source(connector_id, config or {})
        result = source.check()
        return {"ok": bool(getattr(result, "success", result)), "result": _jsonable(result)}

    def read(self, request: AirbyteEmbeddedReadRequest) -> dict[str, Any]:
        connector = get_connector(request.connector_id)
        selected = request.streams or [stream.name for stream in connector.streams]
        if request.dry_run:
            return {
                "dry_run": True,
                "connector_id": connector.id,
                "streams": selected,
                "limit": request.limit,
                "cache_path": str(self.cache_root / (request.cache_name or connector.id)),
                "records": [],
            }

        source = self._pyairbyte_source(request.connector_id, request.config)
        cache = self._default_cache(request.cache_name or connector.id)
        result = source.read(cache=cache, streams=selected)
        return {
            "dry_run": False,
            "connector_id": connector.id,
            "streams": selected,
            "cache_path": str(self.cache_root / (request.cache_name or connector.id)),
            "result": _jsonable(result),
        }

    def _pyairbyte_source(self, connector_id: str, config: dict[str, Any]) -> Any:
        connector = get_connector(connector_id)
        try:
            import airbyte as ab  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("PyAirbyte is not installed; use dry_run=true") from exc

        source_name = connector.python_package or connector.id
        return ab.get_source(source_name, config=config)

    def _default_cache(self, cache_name: str) -> Any:
        try:
            import airbyte as ab  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("PyAirbyte is not installed; use dry_run=true") from exc
        self.cache_root.mkdir(parents=True, exist_ok=True)
        return ab.new_local_cache(str(self.cache_root / cache_name))


def _catalog_payload(streams: list[AirbyteStreamSpec], *, source: str) -> dict[str, Any]:
    return {
        "source": source,
        "catalog": {
            "streams": [
                {
                    "name": stream.name,
                    "namespace": stream.namespace,
                    "json_schema": stream.json_schema,
                    "supported_sync_modes": [mode.value for mode in stream.supported_sync_modes],
                    "default_sync_mode": stream.default_sync_mode.value,
                    "cursor_field": stream.cursor_field,
                    "primary_key": stream.primary_key,
                    "selected": stream.selected,
                }
                for stream in streams
            ]
        },
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return repr(value)


__all__ = ["EmbeddedAirbyteRunner"]
