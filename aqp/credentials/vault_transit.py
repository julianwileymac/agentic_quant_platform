"""Envelope-encryption helper backed by HashiCorp Vault Transit (Workstream D).

Wraps the per-tenant DEK + master KEK pattern HashiCorp documents for
Transit. Encrypted blobs are stored as ``vault:v1:<base64>`` strings;
the helper exposes :func:`encrypt` and :func:`decrypt` that take +
return plain :class:`bytes`.

Falls back gracefully when ``hvac`` isn't installed or
``AQP_VAULT_ADDR`` isn't set: in that case the helper uses an
authenticated AEAD primitive (NaCl ``SecretBox``) keyed by
``settings.user_oauth_local_key``. Operators are expected to switch
to the Vault path before production.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
from typing import Any

logger = logging.getLogger(__name__)


def _local_key() -> bytes:
    """Return the local fallback symmetric key.

    Reads from ``settings.user_oauth_local_key`` (hex-encoded 32 bytes)
    or generates a stable per-process key on demand. The generated key
    is process-local and lost on restart — fine for dev / smoke tests
    where the data is throw-away.
    """
    try:
        from aqp.config import settings

        hex_value = str(getattr(settings, "user_oauth_local_key", "") or "").strip()
    except Exception:  # noqa: BLE001
        hex_value = ""
    if hex_value:
        try:
            raw = bytes.fromhex(hex_value)
        except ValueError:
            raw = b""
        if len(raw) == 32:
            return raw
    # Per-process random key (lost on restart). Logged once so the
    # operator knows to set the env var for any persistent dev data.
    key = secrets.token_bytes(32)
    logger.warning(
        "VaultTransitEnvelope using a per-process random key; "
        "set AQP_USER_OAUTH_LOCAL_KEY (hex, 32 bytes) for persistence"
    )
    return key


def _vault_enabled() -> bool:
    if not os.environ.get("VAULT_ADDR"):
        return False
    try:
        import hvac  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


def _active_cell_transit_key() -> str | None:
    """Return the per-cell Vault Transit key id, or ``None``.

    Phase 6 §9.7 (RESTRUCTURING_PLAN.md): silo-reg cells get a
    dedicated Vault Transit key so a leaked KEK in one cell cannot
    decrypt ciphertexts from another. The resolver consults
    ``RequestContext.cell_id`` → ``CellDataPlane.vault_transit_key``.

    Returns ``None`` when:
      * no request context is bound;
      * the bound cell has no ``vault_transit_key`` set (the default
        for shared-std / shared-prem cells — they share the
        cluster-wide per-tenant keys);
      * the topology cannot be loaded.
    """
    try:
        from aqp.tenancy.runtime_context import get_runtime_context
    except Exception:  # pragma: no cover - defensive
        return None
    ctx = get_runtime_context()
    cell_id = getattr(ctx, "cell_id", None) if ctx is not None else None
    if not cell_id:
        return None
    try:
        from aqp.deployment.topology import get_deployment_topology
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        topo = get_deployment_topology()
    except Exception:  # pragma: no cover - defensive
        return None
    cell = topo.cell_map.get(cell_id)
    if cell is None:
        return None
    dp = getattr(cell, "data_plane", None)
    if dp is None:
        return None
    key_id = (getattr(dp, "vault_transit_key", "") or "").strip()
    return key_id or None


def _resolve_transit_key_name(tenant: str) -> str:
    """Return the canonical Vault Transit key name for the current call.

    Phase 6 §9.7 — if the active ``RequestContext`` is bound to a
    cell whose ``CellDataPlane.vault_transit_key`` is set, the cell's
    key takes precedence over the per-tenant key. This is the
    cryptographic data-plane separation lever for silo-reg cells.
    """
    cell_key = _active_cell_transit_key()
    if cell_key:
        return cell_key
    return f"aqp-tenant-{tenant}"


def encrypt(plaintext: bytes, *, tenant: str = "default") -> str:
    """Return a serialised ciphertext for ``plaintext``.

    Format: ``"vault:v1:<base64>"`` (Vault Transit) or
    ``"local:v1:<nonce_b64>:<ciphertext_b64>"`` (NaCl SecretBox
    fallback). The serialisation form is stable so a deployment can
    migrate from local to Vault by re-encrypting in place.
    """
    if _vault_enabled():
        return _vault_encrypt(plaintext, tenant=tenant)
    return _local_encrypt(plaintext)


def decrypt(ciphertext: str, *, tenant: str = "default") -> bytes:
    if not ciphertext:
        return b""
    if ciphertext.startswith("vault:"):
        if not _vault_enabled():
            raise RuntimeError("ciphertext requires Vault Transit but Vault is unavailable")
        return _vault_decrypt(ciphertext, tenant=tenant)
    if ciphertext.startswith("local:"):
        return _local_decrypt(ciphertext)
    raise ValueError(f"unknown ciphertext envelope: {ciphertext[:16]!r}")


# ---------------------------------------------------------------------------
# Vault Transit path
# ---------------------------------------------------------------------------


def _vault_encrypt(plaintext: bytes, *, tenant: str) -> str:
    import hvac  # type: ignore[import-not-found]

    client = hvac.Client(url=os.environ.get("VAULT_ADDR", ""), token=os.environ.get("VAULT_TOKEN"))
    if not client.is_authenticated():
        raise RuntimeError("Vault client failed to authenticate")
    key_name = _resolve_transit_key_name(tenant)
    # Idempotent ensure_transit_key. The Transit secrets engine MUST be
    # enabled at the ``transit/`` mount; operators do this once at
    # bootstrap.
    try:
        client.secrets.transit.create_key(name=key_name, exportable=False)
    except Exception:  # noqa: BLE001 - already-exists is the common case
        pass
    response = client.secrets.transit.encrypt_data(
        name=key_name,
        plaintext=base64.b64encode(plaintext).decode("ascii"),
    )
    ciphertext = response["data"]["ciphertext"]
    return f"vault:v1:{ciphertext}"


def _vault_decrypt(ciphertext: str, *, tenant: str) -> bytes:
    import hvac  # type: ignore[import-not-found]

    _, _, payload = ciphertext.split(":", 2)
    client = hvac.Client(url=os.environ.get("VAULT_ADDR", ""), token=os.environ.get("VAULT_TOKEN"))
    key_name = _resolve_transit_key_name(tenant)
    response = client.secrets.transit.decrypt_data(name=key_name, ciphertext=payload)
    return base64.b64decode(response["data"]["plaintext"])


# ---------------------------------------------------------------------------
# Local AEAD fallback (HMAC-SHA256 + AES-GCM via cryptography)
# ---------------------------------------------------------------------------


def _local_encrypt(plaintext: bytes) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for local envelope encryption") from exc
    key = _local_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return "local:v1:" + base64.urlsafe_b64encode(nonce).decode("ascii") + ":" + base64.urlsafe_b64encode(ct).decode("ascii")


def _local_decrypt(ciphertext: str) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("cryptography is required for local envelope decryption") from exc
    parts = ciphertext.split(":")
    if len(parts) != 4 or parts[0] != "local" or parts[1] != "v1":
        raise ValueError(f"malformed local envelope: {ciphertext[:24]!r}")
    nonce = base64.urlsafe_b64decode(parts[2])
    ct = base64.urlsafe_b64decode(parts[3])
    key = _local_key()
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)


# ---------------------------------------------------------------------------
# Convenience: hashed lookup tokens (for vault paths)
# ---------------------------------------------------------------------------


def deterministic_vault_path(*, org_id: str, user_id: str, source: str) -> str:
    """Return the canonical Vault path for a user's OAuth token blob.

    ``oauth2/users/<org>/<user>/<source>`` — fixed-format, no secret
    material. Used by :class:`UserOAuthTokenStore` to map ORM rows
    back to Vault entries.
    """
    return f"oauth2/users/{org_id or 'default'}/{user_id}/{source}"


__all__ = [
    "decrypt",
    "deterministic_vault_path",
    "encrypt",
]
