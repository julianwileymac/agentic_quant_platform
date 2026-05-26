"""TransparencyAnchorSink ABC + self-registering metaclass (Phase 7).

Mirrors :class:`aqp.credentials.protocol.SecretStoreMeta` and
:class:`aqp.auth.providers.protocol.IdentityProviderMeta`. Subclasses
set ``sink_kind`` (the dispatch key matched against
``settings.audit_transparency_sink``) and the metaclass calls
:func:`aqp.core.registry.register` automatically so introspection
endpoints can enumerate them without a manual decorator.

Lifecycle surface every sink exposes:

- :meth:`anchor(record)` — submit one :class:`AnchorRecord`; the sink
  returns a sink-specific verification handle (Rekor entry UUID, QLDB
  document id, RFC 3161 TimeStampResp blob).
- :meth:`verify(record, handle)` — verify a previously-anchored record
  against the sink. Used by the reconstruction harness in Phase 7.5.
- :meth:`describe()` — safe diagnostic surface (no secrets).
"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

from aqp.core.registry import register

logger = logging.getLogger(__name__)


TRANSPARENCY_ANCHOR_SINK_KIND = "transparency_anchor_sink"


@dataclass(frozen=True)
class AnchorRecord:
    """One audit-segment tip-hash record submitted to a transparency log.

    Phase 7 §10.1 — every closed audit segment publishes:

    - ``cell_id`` — which cell produced the segment.
    - ``segment_start_ts`` / ``segment_end_ts`` — the hour boundary.
    - ``prev_tip_hash`` — the previous segment's last-row hash (links
      segments into the global chain).
    - ``tip_hash`` — the last-row hash for this segment.
    - ``iceberg_snapshot_id`` — the Iceberg snapshot id that materialised
      this segment to the audit lake.
    - ``s3_manifest_uri`` — full s3:// URI of the manifest copied with
      Object Lock COMPLIANCE.

    The sink converts these to whatever format the underlying log
    requires (Rekor JSON payload, QLDB document, RFC 3161 TimeStampReq
    digest).
    """

    cell_id: str
    segment_start_ts: datetime
    segment_end_ts: datetime
    prev_tip_hash: bytes | None
    tip_hash: bytes
    iceberg_snapshot_id: str
    s3_manifest_uri: str
    extra: dict[str, Any] = field(default_factory=dict)


class TransparencyAnchorSinkMeta(ABCMeta):
    """Metaclass that auto-registers concrete :class:`TransparencyAnchorSink` classes.

    Skips abstract bases (``__abstract_sink__ = True`` or names
    starting with ``Base`` / ``_``).
    """

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_sink__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        kind = getattr(cls, "sink_kind", None)
        if not kind:
            return cls
        alias = getattr(cls, "sink_alias", None) or cls.__name__
        try:
            register(
                name=alias,
                kind=TRANSPARENCY_ANCHOR_SINK_KIND,
                source=str(kind),
            )(cls)
        except Exception:  # noqa: BLE001 - never fail import on registry hiccup
            logger.debug(
                "TransparencyAnchorSink auto-registration failed for %s",
                name,
                exc_info=True,
            )
        return cls


class TransparencyAnchorSink(metaclass=TransparencyAnchorSinkMeta):
    """Pluggable transparency-log anchor sink.

    Phase 7 §10.1 — three sinks ship with AQP:

    - :class:`RekorSink` (``sink_kind="rekor"``) — public sigstore
      Rekor; ideal for ``shared-std`` / ``shared-prem`` cells.
    - :class:`QLDBSink` (``sink_kind="qldb"``) — AWS QLDB; ideal for
      ``silo-reg``-on-AWS cells.
    - :class:`Rfc3161TsaSink` (``sink_kind="rfc3161"``) — external RFC
      3161 TSA; ideal for ``silo-reg``-on-prem cells.

    Subclasses set ``sink_kind`` (the dispatch key the factory matches
    against ``settings.audit_transparency_sink``) and ``sink_alias``
    (optional; defaults to the class name).
    """

    __abstract_sink__: ClassVar[bool] = True

    sink_kind: ClassVar[str] = ""
    sink_alias: ClassVar[str | None] = None

    @abstractmethod
    def anchor(self, record: AnchorRecord) -> str:
        """Submit ``record`` to the transparency log.

        Returns a sink-specific verification handle (Rekor entry UUID,
        QLDB document id, base64 RFC 3161 TimeStampResp). The caller
        (the audit_lake_tasks.flush job) persists this handle alongside
        the segment so the evidence bundle can replay the proof.
        """

    @abstractmethod
    def verify(self, record: AnchorRecord, handle: str) -> bool:
        """Verify a previously-anchored ``record`` against ``handle``.

        Used by ``aqp.audit.replay.replay_run`` to confirm an audit
        segment hasn't been tampered with since anchoring.
        """

    def describe(self) -> dict[str, Any]:
        """Safe diagnostic surface — no secrets."""
        return {
            "kind": self.sink_kind,
            "alias": self.sink_alias or self.__class__.__name__,
        }

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)


def list_transparency_anchor_sink_classes() -> dict[str, type[TransparencyAnchorSink]]:
    """Return ``{alias: class}`` for every registered sink."""
    from aqp.core.registry import list_by_kind

    out: dict[str, type[TransparencyAnchorSink]] = {}
    for alias, cls in list_by_kind(TRANSPARENCY_ANCHOR_SINK_KIND).items():
        if isinstance(cls, type) and issubclass(cls, TransparencyAnchorSink):
            out[alias] = cls
    return out


__all__ = [
    "AnchorRecord",
    "TRANSPARENCY_ANCHOR_SINK_KIND",
    "TransparencyAnchorSink",
    "TransparencyAnchorSinkMeta",
    "list_transparency_anchor_sink_classes",
]
