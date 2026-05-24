"""Per-actor Ed25519 signing-key issuance for lineage (Workstream C).

Pairs with :mod:`aqp.auth.signing`. This module provides the
operational hooks for issuing, archiving, and rotating signing keys:

- :func:`issue_signing_key(actor)` — generate a fresh Ed25519
  keypair, persist the public half into the
  :class:`SigningKeyArchive` table, and return the private material
  so the caller can hand it to :class:`CredentialResolver` /
  Vault PKI.
- :func:`archive_public_key(...)` — record an existing public key
  alongside its ``key_id`` so verifiers can fetch it after rotation.
- :func:`get_public_key_for(key_id)` — verifier-side lookup that
  underlies the audit / replay path.

We deliberately do NOT bake the Vault PKI HTTP calls into this
module: the existing :class:`HashicorpVaultSecretStore` already
handles the Vault auth + secret read; this module focuses on the
durable Postgres archive that maps ``key_id`` -> public key PEM. The
archive is the source of truth that lets us verify a six-month-old
lineage row even after the active key has rotated three times.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aqp.auth.signing import ActorIdentity, SigningKeyMaterial

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


def generate_ed25519_keypair() -> tuple[bytes, str, str]:
    """Return ``(seed_32_bytes, private_pem, public_pem)``.

    Uses ``cryptography`` (already a transitive dep via
    ``python-jose[cryptography]``) so this module stays import-safe
    even when ``pynacl`` is absent. The 32-byte seed is the canonical
    Ed25519 private key per RFC 8032 §5.1.5.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )  # type: ignore[import-not-found]
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Ed25519 key generation requires 'cryptography' to be installed"
        ) from exc

    private = Ed25519PrivateKey.generate()
    seed = private.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    pem = private.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    ).decode("utf-8")
    public_pem = private.public_key().public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return seed, pem, public_pem


# ---------------------------------------------------------------------------
# Archive lookups
# ---------------------------------------------------------------------------


def get_public_key_for(key_id: str) -> str:
    """Return the archived public key PEM for ``key_id``, or empty string.

    Used by downstream verifiers to validate a historical signature.
    The archive table (``lineage_signing_key_archive``) is created in
    the workstream A migration; this function lazy-imports the ORM so
    the helper stays usable before the migration has been applied
    (returns empty string in that case).
    """
    if not key_id or key_id == "null":
        return ""
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_signing_keys import SigningKeyArchive
    except Exception:  # noqa: BLE001
        return ""
    try:
        with get_session() as session:
            row = (
                session.query(SigningKeyArchive)
                .filter(SigningKeyArchive.key_id == key_id)
                .one_or_none()
            )
            if row is None:
                return ""
            return str(row.public_key_pem or "")
    except Exception:  # noqa: BLE001
        logger.debug("public-key lookup failed for key_id=%s", key_id, exc_info=True)
        return ""


def archive_public_key(
    *,
    key_id: str,
    public_key_pem: str,
    actor: ActorIdentity,
    ttl_days: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record ``public_key_pem`` alongside ``key_id`` in the archive.

    Idempotent: re-archiving the same ``key_id`` is a no-op (the
    archive is append-only by design — keys are immutable once
    minted). The ``ttl_days`` knob is advisory only — the archive
    keeps keys forever so historical signatures stay verifiable; the
    field is used by the rotation runbook to decide when to stop
    minting fresh signatures with this key.
    """
    if not key_id or not public_key_pem:
        return
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_signing_keys import SigningKeyArchive
    except Exception:  # noqa: BLE001
        logger.warning("signing-key archive unavailable; skipping archive of %s", key_id)
        return

    expires_at = None
    if ttl_days is not None and ttl_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=int(ttl_days))

    try:
        with get_session() as session:
            existing = (
                session.query(SigningKeyArchive)
                .filter(SigningKeyArchive.key_id == key_id)
                .one_or_none()
            )
            if existing is not None:
                return
            row = SigningKeyArchive(
                key_id=key_id,
                public_key_pem=public_key_pem,
                actor_kind=actor.kind,
                actor_ref=actor.ref,
                meta_json=dict(metadata or {}),
                expires_at=expires_at,
            )
            session.add(row)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("failed to archive signing key %s", key_id, exc_info=True)


# ---------------------------------------------------------------------------
# Issuance
# ---------------------------------------------------------------------------


def issue_signing_key(
    actor: ActorIdentity,
    *,
    ttl_days: int = 365,
) -> SigningKeyMaterial:
    """Generate + archive a fresh Ed25519 key for ``actor``.

    The caller is responsible for handing the resulting
    :class:`SigningKeyMaterial` to the appropriate credential store
    (Vault, KV, etc.) so :func:`aqp.auth.signing.get_signer_for` can
    later resolve it. The public half is persisted to the archive
    BEFORE the function returns so a verifier always has the data
    needed to validate signatures the caller is about to mint.
    """
    seed, private_pem, public_pem = generate_ed25519_keypair()
    key_id = _derive_key_id(actor, seed)
    archive_public_key(
        key_id=key_id,
        public_key_pem=public_pem,
        actor=actor,
        ttl_days=ttl_days,
    )
    return SigningKeyMaterial(
        key_id=key_id,
        private_key_pem=private_pem,
        private_key_bytes=seed,
        public_key_pem=public_pem,
    )


def _derive_key_id(actor: ActorIdentity, seed: bytes) -> str:
    """Deterministic ``key_id`` for tracing.

    Format: ``ed25519:<actor_kind>:<short_b64>``. The short base64
    chunk is the first 12 chars of the SHA-256-of-seed digest — long
    enough to disambiguate within a tenant, short enough to fit on a
    log line without dominating it.
    """
    import hashlib

    digest = hashlib.sha256(seed).digest()
    short = base64.urlsafe_b64encode(digest)[:12].decode("ascii")
    kind = (actor.kind or "service").strip().lower() or "service"
    return f"ed25519:{kind}:{short}"


__all__ = [
    "archive_public_key",
    "generate_ed25519_keypair",
    "get_public_key_for",
    "issue_signing_key",
]
