"""Transparency-log anchor sink adapters (Phase 7 §10.1).

Import every concrete sink at package import so the
:class:`TransparencyAnchorSinkMeta` metaclass auto-registers it.
"""
from __future__ import annotations

from aqp.audit.sinks.rekor import RekorSink
from aqp.audit.sinks.qldb import QLDBSink
from aqp.audit.sinks.rfc3161 import Rfc3161TsaSink

__all__ = [
    "QLDBSink",
    "RekorSink",
    "Rfc3161TsaSink",
]
