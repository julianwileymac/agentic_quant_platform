"""Append-only archive of Ed25519 public keys used by the lineage layer.

Pairs with :mod:`aqp.auth.signing` and :mod:`aqp.auth.signing_keys`.
Every transform vertex in the bipartite lineage ledger (workstream A)
carries a ``signing_key_id``; verifiers fetch the matching public key
from this table to validate the signature.

The table is intentionally separate from the lineage tables themselves
so the rotation cadence (potentially per-shift for service keys,
per-onboard for user keys) doesn't bloat the high-cardinality vertex
tables. Rows are immutable once written — the same key_id maps to the
same public key forever; rotation produces a NEW key_id.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Index, String, Text

from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class SigningKeyArchive(Base):
    """One row per Ed25519 public key minted by the platform.

    ``key_id`` is the stable, signature-portable identifier
    (:func:`aqp.auth.signing_keys._derive_key_id`). ``public_key_pem``
    is the SubjectPublicKeyInfo PEM blob; ``actor_kind`` /
    ``actor_ref`` record who the key was minted for so an auditor can
    cross-reference against the existing tenancy + agent registries.

    The ``expires_at`` column is advisory: it tells the rotation
    runbook when to stop minting fresh signatures with this key, NOT
    when to delete the row. Archive rows are kept forever so historic
    signatures stay verifiable.
    """

    __tablename__ = "lineage_signing_key_archive"

    id = Column(String(36), primary_key=True, default=_uuid)
    key_id = Column(String(96), nullable=False, unique=True, index=True)
    public_key_pem = Column(Text, nullable=False)

    actor_kind = Column(String(32), nullable=False, index=True)
    actor_ref = Column(String(128), nullable=False, index=True)

    meta_json = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_signing_key_archive_actor", "actor_kind", "actor_ref"),
    )


__all__ = ["SigningKeyArchive"]
