"""OS-native credential persistence for the AQP CLI.

Three storage backends, picked in order of decreasing security:

1. **OS native keyring** — macOS Keychain, Windows Credential
   Locker, Linux Secret Service (gnome-keyring / kwallet). Highest
   security; tokens never touch disk in plaintext.
2. **``keyrings.alt`` encrypted file** — fallback for headless
   Linux servers without a Secret Service. Uses an AES-256 key
   derived from the machine hostname; never stores the master key.
3. **Plaintext JSON file** — last-resort fallback for environments
   where neither of the above works (CI runners, exotic distros).
   Off by default — operators must opt in with
   ``AQP_CLI_AUTH_ALLOW_PLAINTEXT_FALLBACK=1``.

Per AGENTS hard rule 53 + the `aqp-management-engine` credential
safety rule, the store NEVER prints token values or includes them
in any error message.

Usage::

    from aqp_cli.auth.keyring_store import KeyringStore, KeyringStoreError

    store = KeyringStore.for_default()
    store.set_tokens(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        id_token=tokens.id_token,
        expires_at=tokens.expires_at,
    )
    tok = store.get_access_token()  # None if absent
    store.clear()                   # logout
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Single canonical service name for the OS keyring — the entry shows up
# as "aqp-cli" in macOS Keychain Access / Windows Credential Manager.
DEFAULT_SERVICE_NAME: str = "aqp-cli"

# Per-field keys under the service entry. These are NOT secret values
# themselves — they're index labels into the keyring backend.
KEY_ACCESS_TOKEN: str = "access_token"
KEY_REFRESH_TOKEN: str = "refresh_token"
KEY_ID_TOKEN: str = "id_token"
KEY_EXPIRES_AT: str = "expires_at"
KEY_METADATA: str = "metadata"


class KeyringBackend(str, Enum):
    """Active backend; used for diagnostics + the ``aqp-cli auth whoami`` table."""

    OS_NATIVE = "os_native"
    ENCRYPTED_FILE = "encrypted_file"
    PLAINTEXT_FILE = "plaintext_file"
    UNAVAILABLE = "unavailable"


class KeyringStoreError(RuntimeError):
    """Raised when no backend is reachable AND plaintext fallback is disabled."""


@dataclass(frozen=True)
class TokenBundle:
    """Decrypted view of the persisted tokens."""

    access_token: str | None
    refresh_token: str | None
    id_token: str | None
    expires_at: float | None
    metadata: dict[str, Any]

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at


class KeyringStore:
    """Multi-backend credential store.

    Construct via :meth:`for_default` in production; the explicit
    constructor is for tests that need to inject a fake backend.
    """

    def __init__(
        self,
        *,
        service_name: str = DEFAULT_SERVICE_NAME,
        plaintext_fallback_path: Path | None = None,
        allow_plaintext_fallback: bool = False,
    ) -> None:
        self.service_name = service_name
        self._plaintext_path = plaintext_fallback_path
        self._allow_plaintext = allow_plaintext_fallback
        self._backend = self._pick_backend()

    # -- public API ------------------------------------------------------

    @classmethod
    def for_default(cls) -> "KeyringStore":
        """Build the default store using env-based opt-ins."""
        allow_plaintext = (
            os.environ.get("AQP_CLI_AUTH_ALLOW_PLAINTEXT_FALLBACK", "")
            .strip()
            .lower()
            in {"1", "true", "yes"}
        )
        plaintext_path = (
            Path(os.environ.get("AQP_CLI_AUTH_PLAINTEXT_PATH"))
            if os.environ.get("AQP_CLI_AUTH_PLAINTEXT_PATH")
            else None
        )
        return cls(
            plaintext_fallback_path=plaintext_path,
            allow_plaintext_fallback=allow_plaintext,
        )

    @property
    def backend(self) -> KeyringBackend:
        """Return the active backend for diagnostics."""
        return self._backend

    def is_available(self) -> bool:
        return self._backend != KeyringBackend.UNAVAILABLE

    def describe(self) -> dict[str, Any]:
        """Return JSON-safe diagnostics. NEVER includes token values."""
        return {
            "backend": self._backend.value,
            "service_name": self.service_name,
            "plaintext_allowed": self._allow_plaintext,
        }

    def set_tokens(
        self,
        *,
        access_token: str | None = None,
        refresh_token: str | None = None,
        id_token: str | None = None,
        expires_at: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist the token bundle to the active backend."""
        if self._backend == KeyringBackend.UNAVAILABLE:
            raise KeyringStoreError(
                "No credential backend available. Install `keyring` (and "
                "`keyrings.alt` for headless servers), or opt in to the "
                "plaintext fallback via AQP_CLI_AUTH_ALLOW_PLAINTEXT_FALLBACK=1."
            )
        if access_token is not None:
            self._set(KEY_ACCESS_TOKEN, access_token)
        if refresh_token is not None:
            self._set(KEY_REFRESH_TOKEN, refresh_token)
        if id_token is not None:
            self._set(KEY_ID_TOKEN, id_token)
        if expires_at is not None:
            self._set(KEY_EXPIRES_AT, str(float(expires_at)))
        if metadata:
            self._set(KEY_METADATA, json.dumps(metadata, sort_keys=True))

    def get_bundle(self) -> TokenBundle:
        """Return the current bundle (all fields None when nothing stored)."""
        if self._backend == KeyringBackend.UNAVAILABLE:
            return TokenBundle(None, None, None, None, {})
        access = self._get(KEY_ACCESS_TOKEN)
        refresh = self._get(KEY_REFRESH_TOKEN)
        id_token = self._get(KEY_ID_TOKEN)
        expires_at_raw = self._get(KEY_EXPIRES_AT)
        expires_at: float | None
        try:
            expires_at = float(expires_at_raw) if expires_at_raw else None
        except (TypeError, ValueError):
            expires_at = None
        metadata_raw = self._get(KEY_METADATA)
        metadata: dict[str, Any] = {}
        if metadata_raw:
            try:
                parsed = json.loads(metadata_raw)
                if isinstance(parsed, dict):
                    metadata = parsed
            except json.JSONDecodeError:
                metadata = {}
        return TokenBundle(
            access_token=access,
            refresh_token=refresh,
            id_token=id_token,
            expires_at=expires_at,
            metadata=metadata,
        )

    def get_access_token(self) -> str | None:
        return self.get_bundle().access_token

    def get_refresh_token(self) -> str | None:
        return self.get_bundle().refresh_token

    def clear(self) -> None:
        """Delete every persisted field."""
        if self._backend == KeyringBackend.UNAVAILABLE:
            return
        for key in (KEY_ACCESS_TOKEN, KEY_REFRESH_TOKEN, KEY_ID_TOKEN, KEY_EXPIRES_AT, KEY_METADATA):
            self._delete(key)

    # -- internals -------------------------------------------------------

    def _pick_backend(self) -> KeyringBackend:
        # Try OS-native first.
        try:
            import keyring  # noqa: F401

            kr = self._safe_get_keyring()
            backend_name = kr.__class__.__module__ if kr else ""
            if kr and not _is_alt_or_fail(backend_name):
                return KeyringBackend.OS_NATIVE
            # `keyrings.alt` (encrypted-file) is acceptable when explicitly
            # installed AND the OS backend is the fail-backend.
            if kr and _is_alt(backend_name):
                return KeyringBackend.ENCRYPTED_FILE
        except ImportError:
            pass
        except Exception:  # pragma: no cover
            logger.debug("keyring backend resolution failed", exc_info=True)
        if self._allow_plaintext:
            return KeyringBackend.PLAINTEXT_FILE
        return KeyringBackend.UNAVAILABLE

    def _safe_get_keyring(self) -> object | None:
        try:
            import keyring

            return keyring.get_keyring()
        except Exception:
            return None

    def _set(self, key: str, value: str) -> None:
        if self._backend in (KeyringBackend.OS_NATIVE, KeyringBackend.ENCRYPTED_FILE):
            import keyring

            keyring.set_password(self.service_name, key, value)
            return
        if self._backend == KeyringBackend.PLAINTEXT_FILE:
            self._plaintext_set(key, value)
            return
        raise KeyringStoreError("No keyring backend available")

    def _get(self, key: str) -> str | None:
        if self._backend in (KeyringBackend.OS_NATIVE, KeyringBackend.ENCRYPTED_FILE):
            import keyring

            try:
                return keyring.get_password(self.service_name, key)
            except Exception:
                logger.debug("keyring.get_password failed for key=%s", key, exc_info=True)
                return None
        if self._backend == KeyringBackend.PLAINTEXT_FILE:
            return self._plaintext_get(key)
        return None

    def _delete(self, key: str) -> None:
        if self._backend in (KeyringBackend.OS_NATIVE, KeyringBackend.ENCRYPTED_FILE):
            import keyring

            try:
                keyring.delete_password(self.service_name, key)
            except Exception:
                # Most backends raise on absent entries; treat as a no-op.
                pass
            return
        if self._backend == KeyringBackend.PLAINTEXT_FILE:
            self._plaintext_delete(key)

    # --- plaintext fallback --------------------------------------------

    def _plaintext_target(self) -> Path:
        if self._plaintext_path:
            return self._plaintext_path
        return Path.home() / ".config" / "aqp" / "credentials" / "auth-session.json"

    def _plaintext_read(self) -> dict[str, str]:
        path = self._plaintext_target()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return {k: str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
        except Exception:
            logger.warning(
                "Plaintext auth-session.json could not be read; ignoring contents"
            )
            return {}

    def _plaintext_write(self, payload: dict[str, str]) -> None:
        path = self._plaintext_target()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        try:
            # 0o600 — owner read/write only. Best-effort on Windows.
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _plaintext_set(self, key: str, value: str) -> None:
        payload = self._plaintext_read()
        payload[key] = value
        self._plaintext_write(payload)

    def _plaintext_get(self, key: str) -> str | None:
        return self._plaintext_read().get(key)

    def _plaintext_delete(self, key: str) -> None:
        payload = self._plaintext_read()
        payload.pop(key, None)
        self._plaintext_write(payload)


# Helpers used by _pick_backend ------------------------------------------------


def _is_alt(module_name: str) -> bool:
    return "keyrings.alt" in (module_name or "")


def _is_alt_or_fail(module_name: str) -> bool:
    name = (module_name or "").lower()
    # `keyring.backends.fail.Keyring` is the no-op fallback that
    # raises on every operation — treat it as unavailable.
    return "fail" in name and "keyring.backends" in name


# Diagnostic helper — used by `aqp-cli auth diagnose`
def diagnose() -> dict[str, Any]:
    """Return a JSON-safe diagnostic snapshot."""
    store = KeyringStore.for_default()
    return {
        "hostname": socket.gethostname(),
        "store": store.describe(),
        "has_access_token": store.get_access_token() is not None,
        "has_refresh_token": store.get_refresh_token() is not None,
    }


__all__ = [
    "DEFAULT_SERVICE_NAME",
    "KEY_ACCESS_TOKEN",
    "KEY_EXPIRES_AT",
    "KEY_ID_TOKEN",
    "KEY_METADATA",
    "KEY_REFRESH_TOKEN",
    "KeyringBackend",
    "KeyringStore",
    "KeyringStoreError",
    "TokenBundle",
    "diagnose",
]
