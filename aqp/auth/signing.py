"""Ed25519 signing for lineage transform vertices and other tamper-evident
records (Workstream C).

The bipartite lineage ledger (workstream A) persists a ``transform_vertex``
row for every data motion. To make those rows usable as audit evidence
they are signed with Ed25519 by the actor that produced them — for
service actors a short-lived M2M key, for human actors a per-user
key, for agent actors a per-agent key. Public keys are archived in
:mod:`aqp.persistence.models_signing_keys` (see workstream A) so a
historical signature can be verified even after the active key has
rotated.

Three modes mirror the rest of the platform's enforcement strategy:

- ``off`` — signing is skipped; the ``signature`` column is left
  empty. Used for local dev where no Vault PKI is configured.
- ``permissive`` — attempt to sign; on any failure emit a structured
  warning + populate ``signature=""`` so the row still inserts. Used
  during rollout.
- ``strict`` — fail the row insert if signing fails. Used in
  regulated deployments where every lineage vertex MUST be signed.

Per AGENTS rule 26: all signing-key material resolves through
:class:`aqp.credentials.CredentialResolver`. Concrete deployments back
the store with Vault PKI (the existing ``HashicorpVaultSecretStore``
already handles the secret-engine path); the env / file stores fall
back to a generated dev key so the local loop keeps working.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from aqp.credentials.protocol import CredentialKey
from aqp.credentials.resolver import get_resolver

logger = logging.getLogger(__name__)


SigningMode = Literal["off", "permissive", "strict"]


class LineageSigningError(Exception):
    """Raised in ``strict`` mode when a signing operation fails."""


# ---------------------------------------------------------------------------
# Actor identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActorIdentity:
    """Stable identity of the actor producing a signed record.

    ``kind`` is one of ``"user" | "agent" | "service" | "system"`` —
    the same vocabulary :mod:`aqp.data.catalog.lineage` already uses
    on :class:`LineageEvent.actor_kind`.

    ``ref`` is the canonical reference: for users it is the user UUID;
    for agents the agent alias; for service / system actors a stable
    identifier (e.g. ``"iceberg_catalog"``).

    The signing-key lookup key is derived deterministically by
    :func:`credential_key_for_actor` so the same actor always resolves
    to the same key path in Vault / KV / env.
    """

    kind: str
    ref: str


def credential_key_for_actor(actor: ActorIdentity) -> CredentialKey:
    """Map an actor onto the :class:`CredentialKey` used to fetch its key.

    The mapping is intentionally one-way: a user actor reaches
    ``("lineage_signing", "user:<id>")``; if no per-user key is
    configured the chain falls back to the service-level key
    ``("lineage_signing", "service")`` via the resolver's default
    field merging. This matches the rest of the platform's "more-
    specific stores win, fall back to broader" precedence.
    """
    kind = (actor.kind or "service").strip().lower() or "service"
    ref = (actor.ref or "").strip()
    if kind == "user" and ref:
        return CredentialKey("lineage_signing", f"user:{ref}")
    if kind == "agent" and ref:
        return CredentialKey("lineage_signing", f"agent:{ref}")
    return CredentialKey("lineage_signing", kind)


# ---------------------------------------------------------------------------
# Key material
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SigningKeyMaterial:
    """Resolved Ed25519 key material for one actor.

    ``key_id`` is the stable identifier persisted alongside the
    signature so verifiers can fetch the matching public key from the
    archive. ``private_key_bytes`` is the raw 32-byte seed when
    available; ``private_key_pem`` is the PKCS#8-encoded equivalent
    that ``pynacl`` / ``cryptography`` accept transparently.
    """

    key_id: str
    private_key_pem: str = ""
    private_key_bytes: bytes = b""
    public_key_pem: str = ""


# ---------------------------------------------------------------------------
# Signer protocol
# ---------------------------------------------------------------------------


class _SignerBase:
    key_id: str = ""

    def sign(self, payload: bytes) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


class NullSigner(_SignerBase):
    """Degraded-mode signer: returns an empty signature.

    Used when signing is disabled, no key is configured, or the
    cryptography backend isn't installed. In ``permissive`` mode the
    LineageGraphWriter persists the row with ``signature=""`` and
    ``signing_key_id="null"`` so lineage still works in environments
    that opted out of signing.
    """

    key_id = "null"

    def sign(self, payload: bytes) -> str:
        return ""


class Ed25519Signer(_SignerBase):
    """Ed25519 signer backed by :mod:`pynacl` or :mod:`cryptography`.

    Falls back to ``cryptography`` (which the platform already pulls in
    transitively via ``python-jose[cryptography]``) when ``pynacl``
    isn't installed. The wire-format signature is hex-encoded so it
    stores cleanly in the ``transform_vertex.signature`` TEXT column.
    """

    def __init__(self, material: SigningKeyMaterial) -> None:
        if not material.key_id:
            raise LineageSigningError("Ed25519Signer requires a non-empty key_id")
        self.key_id = material.key_id
        self._material = material
        self._private = self._load_private_key(material)

    @staticmethod
    def _load_private_key(material: SigningKeyMaterial) -> Any:
        # Prefer pynacl when available (smallest dependency surface).
        try:
            from nacl.signing import SigningKey  # type: ignore[import-not-found]

            seed = material.private_key_bytes
            if not seed and material.private_key_pem:
                seed = _seed_from_pem(material.private_key_pem)
            if not seed:
                raise LineageSigningError(
                    f"signing key {material.key_id!r} has neither bytes nor PEM"
                )
            if len(seed) != 32:
                raise LineageSigningError(
                    f"signing key {material.key_id!r} seed length {len(seed)} != 32"
                )
            return SigningKey(seed)
        except ImportError:
            pass
        # Fallback to cryptography.
        try:
            from cryptography.hazmat.primitives.serialization import (
                Encoding,
                NoEncryption,
                PrivateFormat,
                load_pem_private_key,
            )  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - both deps missing is exotic
            raise LineageSigningError(
                "Ed25519 signing requires either 'pynacl' or 'cryptography'"
            ) from exc

        pem = material.private_key_pem
        if not pem:
            raise LineageSigningError(
                f"signing key {material.key_id!r} has no PEM material"
            )
        # Returns an ``Ed25519PrivateKey``.
        return load_pem_private_key(pem.encode("utf-8"), password=None)

    def sign(self, payload: bytes) -> str:
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("payload must be bytes")
        try:
            from nacl.signing import SigningKey  # type: ignore[import-not-found]

            if isinstance(self._private, SigningKey):
                sig = self._private.sign(payload).signature
                return sig.hex()
        except ImportError:
            pass
        # cryptography path: ``Ed25519PrivateKey.sign(payload)`` returns bytes.
        sig_bytes: bytes = self._private.sign(payload)  # type: ignore[attr-defined]
        return sig_bytes.hex()


def _seed_from_pem(pem: str) -> bytes:
    """Extract the 32-byte Ed25519 seed from a PKCS#8 PEM blob."""
    try:
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            load_pem_private_key,
        )  # type: ignore[import-not-found]
    except ImportError:
        return b""
    try:
        key = load_pem_private_key(pem.encode("utf-8"), password=None)
        raw = key.private_bytes(  # type: ignore[attr-defined]
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )
        return raw if isinstance(raw, bytes) else bytes(raw)
    except Exception:  # noqa: BLE001
        return b""


# ---------------------------------------------------------------------------
# Verifier (for tests + downstream consumers)
# ---------------------------------------------------------------------------


def verify_signature(
    *,
    signature_hex: str,
    payload: bytes,
    public_key_pem: str = "",
    public_key_bytes: bytes = b"",
) -> bool:
    """Verify an Ed25519 signature.

    Returns ``True`` iff the signature validates. Never raises — every
    failure (missing crypto lib, malformed key, bad signature) returns
    ``False``. Use this in tests to assert round-trip correctness and
    in downstream auditors to confirm a historical lineage row hasn't
    been tampered with.
    """
    if not signature_hex:
        return False
    try:
        sig = bytes.fromhex(signature_hex)
    except ValueError:
        return False

    # nacl path
    try:
        from nacl.exceptions import BadSignatureError  # type: ignore[import-not-found]
        from nacl.signing import VerifyKey  # type: ignore[import-not-found]

        if public_key_bytes and len(public_key_bytes) == 32:
            try:
                VerifyKey(public_key_bytes).verify(payload, sig)
                return True
            except BadSignatureError:
                return False
    except ImportError:
        pass
    # cryptography path
    try:
        from cryptography.exceptions import InvalidSignature  # type: ignore[import-not-found]
        from cryptography.hazmat.primitives.serialization import (
            load_pem_public_key,
        )  # type: ignore[import-not-found]

        if not public_key_pem:
            return False
        pub = load_pem_public_key(public_key_pem.encode("utf-8"))
        try:
            pub.verify(sig, payload)  # type: ignore[attr-defined]
            return True
        except InvalidSignature:
            return False
        except Exception:  # noqa: BLE001
            return False
    except ImportError:
        return False
    return False


# ---------------------------------------------------------------------------
# Canonical encoding
# ---------------------------------------------------------------------------


def canonical_transform_payload(
    *,
    job_name: str,
    run_id: str,
    code_version: str,
    parameters: dict[str, Any] | None,
    input_hashes: list[str] | None,
    output_hashes: list[str] | None,
) -> bytes:
    """Canonical byte payload signed by :class:`Ed25519Signer`.

    The plan calls this out explicitly: the signature covers
    ``canonical(job_name || run_id || code_version ||
    sorted(parameters) || sorted(input_hashes) || sorted(output_hashes))``.

    We achieve canonicalisation by:

    - Sorting every dict key recursively (``json.dumps(...,
      sort_keys=True)``).
    - Sorting list inputs (``sorted(...)``).
    - Encoding without whitespace (``separators=(",",":")``).
    - UTF-8-encoding the resulting JSON.

    The resulting payload is also hashed with SHA-256 BEFORE
    signing so the on-the-wire signature is constant-size regardless
    of how large the parameters dict gets — matches the lineage_graph
    schema's intent (signed payload is one row, indexable).
    """
    payload_obj: dict[str, Any] = {
        "job_name": str(job_name or ""),
        "run_id": str(run_id or ""),
        "code_version": str(code_version or ""),
        "parameters": _canonical_dict(parameters or {}),
        "input_hashes": sorted(str(h) for h in (input_hashes or [])),
        "output_hashes": sorted(str(h) for h in (output_hashes or [])),
    }
    canonical = json.dumps(payload_obj, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).digest()
    return digest


def _canonical_dict(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _canonical_dict(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list):
        return [_canonical_dict(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_dict(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Signing-mode resolver
# ---------------------------------------------------------------------------


def get_signing_mode() -> SigningMode:
    """Read ``settings.lineage_signing_mode`` (workstream C)."""
    try:
        from aqp.config import settings

        if not bool(getattr(settings, "lineage_signing_enabled", False)):
            return "off"
        raw = str(getattr(settings, "lineage_signing_mode", "permissive") or "permissive").lower()
    except Exception:  # noqa: BLE001
        return "off"
    if raw in ("off", "permissive", "strict"):
        return raw  # type: ignore[return-value]
    return "permissive"


# ---------------------------------------------------------------------------
# Per-actor signer cache
# ---------------------------------------------------------------------------


_SIGNER_CACHE: dict[str, _SignerBase] = {}
_SIGNER_LOCK = threading.RLock()


def _cache_key(actor: ActorIdentity) -> str:
    return f"{actor.kind}:{actor.ref}"


def reset_signer_cache() -> None:
    """Drop the in-process signer cache (tests + key-rotation runbook)."""
    with _SIGNER_LOCK:
        _SIGNER_CACHE.clear()


def get_signer_for(actor: ActorIdentity) -> _SignerBase:
    """Resolve the active signer for ``actor``.

    Honours :func:`get_signing_mode`:

    - ``off`` -> always returns a :class:`NullSigner`.
    - ``permissive`` / ``strict`` -> resolves the key via
      :class:`CredentialResolver`; on failure returns a
      :class:`NullSigner` in permissive mode or raises
      :class:`LineageSigningError` in strict mode.

    The resolved signer is cached per-actor in-process for the
    lifetime of the worker; rotation is handled by
    :func:`reset_signer_cache` after a key change.
    """
    mode = get_signing_mode()
    if mode == "off":
        return NullSigner()

    cache_key = _cache_key(actor)
    with _SIGNER_LOCK:
        cached = _SIGNER_CACHE.get(cache_key)
        if cached is not None:
            return cached

    material = _resolve_key_material(actor)
    if material is None:
        if mode == "strict":
            raise LineageSigningError(
                f"no signing key configured for actor {actor.kind}:{actor.ref}"
            )
        signer: _SignerBase = NullSigner()
    else:
        try:
            signer = Ed25519Signer(material)
        except LineageSigningError:
            if mode == "strict":
                raise
            logger.warning(
                "lineage signing falling back to NullSigner for actor=%s:%s",
                actor.kind,
                actor.ref,
            )
            signer = NullSigner()

    with _SIGNER_LOCK:
        _SIGNER_CACHE[cache_key] = signer
    return signer


def _resolve_key_material(actor: ActorIdentity) -> SigningKeyMaterial | None:
    """Pull key material via :class:`CredentialResolver`.

    Returns ``None`` when the chain reports the key is absent — the
    caller decides whether that's fatal (strict mode) or degraded
    (permissive mode).
    """
    resolver = get_resolver()
    key = credential_key_for_actor(actor)
    try:
        cred = resolver.resolve(key)
    except Exception:  # noqa: BLE001 - never crash the lineage path
        return None
    if not cred or not cred.fields:
        return None

    fields = cred.fields
    key_id = str(fields.get("key_id") or fields.get("kid") or actor.kind).strip()
    private_pem = str(fields.get("private_key_pem") or "").strip()
    public_pem = str(fields.get("public_key_pem") or "").strip()
    seed_b64 = str(fields.get("private_key_seed_b64") or "").strip()
    seed_hex = str(fields.get("private_key_seed_hex") or "").strip()

    private_bytes = b""
    if seed_b64:
        try:
            private_bytes = base64.b64decode(seed_b64, validate=True)
        except Exception:  # noqa: BLE001
            private_bytes = b""
    elif seed_hex:
        try:
            private_bytes = bytes.fromhex(seed_hex)
        except ValueError:
            private_bytes = b""

    if not private_pem and not private_bytes:
        return None
    return SigningKeyMaterial(
        key_id=key_id,
        private_key_pem=private_pem,
        private_key_bytes=private_bytes,
        public_key_pem=public_pem,
    )


# ---------------------------------------------------------------------------
# Top-level helper
# ---------------------------------------------------------------------------


def sign_transform_payload(
    *,
    actor: ActorIdentity,
    job_name: str,
    run_id: str,
    code_version: str,
    parameters: dict[str, Any] | None,
    input_hashes: list[str] | None,
    output_hashes: list[str] | None,
) -> tuple[str, str]:
    """Return ``(signature_hex, signing_key_id)`` for a transform vertex.

    A convenience wrapper used by the LineageGraphWriter (workstream A).
    Honours the configured signing mode end-to-end:

    - ``off`` mode -> ``("", "null")``.
    - ``permissive`` -> best-effort; on failure ``("", "null")``.
    - ``strict`` -> raises :class:`LineageSigningError` on any failure.
    """
    signer = get_signer_for(actor)
    payload = canonical_transform_payload(
        job_name=job_name,
        run_id=run_id,
        code_version=code_version,
        parameters=parameters,
        input_hashes=input_hashes,
        output_hashes=output_hashes,
    )
    try:
        sig = signer.sign(payload)
    except Exception as exc:  # noqa: BLE001
        if get_signing_mode() == "strict":
            raise LineageSigningError(str(exc)) from exc
        logger.warning("lineage signing failed: %s", exc)
        return ("", "null")
    return (sig, signer.key_id or "null")


__all__ = [
    "ActorIdentity",
    "Ed25519Signer",
    "LineageSigningError",
    "NullSigner",
    "SigningKeyMaterial",
    "SigningMode",
    "canonical_transform_payload",
    "credential_key_for_actor",
    "get_signer_for",
    "get_signing_mode",
    "reset_signer_cache",
    "sign_transform_payload",
    "verify_signature",
]
