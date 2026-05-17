"""Sink registry service.

Exposes CRUD over the project-scoped :class:`SinkRow` registry, with
immutable hash-locked :class:`SinkVersionRow` snapshots on every
edit. The companion module :mod:`aqp.data.sinks.service` is the
single entry point used by the ``/sinks`` API routes and the
PipelinesHub / SinkRegistry UI.
"""
from aqp.data.sinks.service import (
    SinkNotFoundError,
    SinkValidationError,
    create_sink,
    delete_sink,
    get_sink,
    list_sink_versions,
    list_sinks,
    materialise_node_spec,
    sink_summary,
    update_sink,
)

__all__ = [
    "SinkNotFoundError",
    "SinkValidationError",
    "create_sink",
    "delete_sink",
    "get_sink",
    "list_sink_versions",
    "list_sinks",
    "materialise_node_spec",
    "sink_summary",
    "update_sink",
]
