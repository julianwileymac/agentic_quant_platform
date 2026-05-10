"""Translate an Airbyte connection spec into a Dagster component config.

Phase 2 produces an :class:`AirbyteConnectionSpec`; the sandbox
turns it into a YAML component file the Dagster sandbox loads on
``execute``. We don't need the full Airbyte / Dagster integration
to be live — the sandbox executor wraps this with mock outputs when
the optional :mod:`dagster_airbyte` package is unavailable.
"""
from __future__ import annotations

from typing import Any


def airbyte_connection_to_component(connection: dict[str, Any]) -> str:
    """Render a Dagster component YAML for ``connection``.

    Output is intentionally minimal — the operator iterates on the
    connector inside the sandbox; the production code-server has the
    real ``AirbyteWorkspaceComponent``. We expose the connector id +
    streams so the sandbox executor can stub the materialisation.
    """
    name = str(connection.get("name") or connection.get("source_connector_id") or "demo")
    streams = connection.get("streams") or []
    stream_block = "\n".join(
        f"  - name: \"{stream.get('name', 'unknown')}\""
        for stream in streams
        if isinstance(stream, dict)
    ) or "  - name: \"default\""
    return (
        "type: airbyte_connection\n"
        f"name: \"{name}\"\n"
        f"source_connector_id: \"{connection.get('source_connector_id', '')}\"\n"
        f"destination_connector_id: \"{connection.get('destination_connector_id', '')}\"\n"
        "streams:\n"
        f"{stream_block}\n"
    )


__all__ = ["airbyte_connection_to_component"]
