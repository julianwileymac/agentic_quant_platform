"""Typed exceptions raised by :mod:`aqp.data.datasets`.

Routes / agents distinguish the different failure modes via these
classes (e.g. an "uningested external" entry raises
:class:`DatasetNotMaterialized` so the discovery browser can offer the
"Promote to Airbyte builder" path instead of dumping a stack trace).
"""
from __future__ import annotations


class DatasetError(Exception):
    """Base class for every error raised by the dataset layer."""


class DatasetKindUnknown(DatasetError):
    """Raised when ``DatasetSpec.kind`` doesn't match a registered subclass."""


class DatasetNotMaterialized(DatasetError):
    """Raised when ``_load`` is invoked on an external-only entry.

    Phase 1 surfaces this directly as a 409 with a "promote-to-ingest"
    handoff.
    """


class DatasetSaveDisabled(DatasetError):
    """Raised when a kind explicitly forbids ``_save`` (e.g. SQL queries)."""


__all__ = [
    "DatasetError",
    "DatasetKindUnknown",
    "DatasetNotMaterialized",
    "DatasetSaveDisabled",
]
