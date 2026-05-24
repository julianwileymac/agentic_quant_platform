"""Unix-domain-socket secret broker sidecar.

Runs as a sidecar container in every kernel pod. On startup it
fetches the calling user's vendor secrets from Vault at
``secret/data/users/<uid>/services/<svc>`` (canonical path per
:mod:`aqp.credentials.vault_transit`) and exposes them via a
Unix domain socket the kernel reads at request time.

The protocol is single-line JSON:

    request:  {"service": "polygon", "label": "primary", "field": "api_key"}
    response: {"ok": true, "value": "<secret>"}
            | {"ok": false, "error": "..."}

The socket is bound to ``/var/run/aqp-secret-broker.sock`` with
mode 0660 + group ``aqp-kernel`` so only the kernel container can
talk to it.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
from typing import Any

logger = logging.getLogger(__name__)


_DEFAULT_SOCKET_PATH = "/var/run/aqp-secret-broker.sock"


class SecretBrokerServer:
    """Single-threaded Unix domain socket server."""

    def __init__(
        self,
        *,
        socket_path: str = _DEFAULT_SOCKET_PATH,
        user_id: str | None = None,
    ) -> None:
        self._socket_path = socket_path
        self._user_id = user_id or os.environ.get("AQP_USER_ID", "anonymous")
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._socket is not None:
            return
        try:
            if os.path.exists(self._socket_path):
                os.unlink(self._socket_path)
        except OSError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self._socket_path)
        sock.listen(8)
        try:
            os.chmod(self._socket_path, 0o660)
        except OSError:
            pass
        self._socket = sock
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        logger.info("aqp secret-broker listening on %s", self._socket_path)

    def stop(self) -> None:
        self._stop.set()
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None
        try:
            if os.path.exists(self._socket_path):
                os.unlink(self._socket_path)
        except OSError:
            pass

    def _serve(self) -> None:
        sock = self._socket
        if sock is None:
            return
        while not self._stop.is_set():
            try:
                conn, _addr = sock.accept()
            except OSError:
                break
            try:
                self._handle(conn)
            finally:
                conn.close()

    def _handle(self, conn: socket.socket) -> None:
        try:
            data = conn.recv(8192)
            req = json.loads(data.decode("utf-8"))
            resp = self._resolve(req)
        except Exception as exc:  # noqa: BLE001
            resp = {"ok": False, "error": str(exc)}
        conn.send(json.dumps(resp).encode("utf-8"))

    def _resolve(self, req: dict[str, Any]) -> dict[str, Any]:
        service = str(req.get("service") or "").strip()
        label = str(req.get("label") or "primary").strip()
        field = str(req.get("field") or "api_key").strip()
        if not service:
            return {"ok": False, "error": "service required"}
        try:
            from aqp.credentials import get_resolver
            from aqp.credentials.protocol import CredentialKey

            bundle = get_resolver().resolve(
                CredentialKey(
                    service=f"{service}:{label}" if label else service,
                    purpose="broker",
                )
            )
            if bundle is None:
                return {"ok": False, "error": "no credential"}
            value = bundle.get(field) or bundle.get("token")
            if not value:
                return {"ok": False, "error": f"field {field!r} missing"}
            return {"ok": True, "value": str(value)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}


__all__ = ["SecretBrokerServer"]
