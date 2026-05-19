"""CloudflareEdgeAdapter — tunnel / DNS / Access app lifecycle.

Mirrors the shape of :class:`aqp.kubernetes.protocol.KubernetesAdapter`:
one process-wide singleton, swappable for tests via
:func:`register_cloudflare_adapter`, methods raise structured errors
that the route + MCP layer translate to HTTP responses.

The adapter ONLY does control-plane / inventory operations — it never
returns secret material. Tunnel secrets, Access app client_secrets, and
DNS API tokens stay inside Cloudflare; the Management Engine subagent
rule forbids logging them.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CloudflareAdapterError(RuntimeError):
    """Base class for adapter-side failures."""


class CloudflareAdapterUnavailable(CloudflareAdapterError):
    """Raised when the adapter cannot service a call (no token, SDK missing)."""


# ---------------------------------------------------------------------------
# Wire-format summaries (compact dataclasses)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TunnelSummary:
    id: str
    name: str
    status: str
    config_src: str = ""
    created_at: str = ""
    deleted_at: str | None = None
    connections: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DnsRecordSummary:
    id: str
    zone_id: str
    name: str
    type: str
    content: str
    ttl: int
    proxied: bool = False
    comment: str = ""


@dataclass(slots=True)
class AccessAppSummary:
    id: str
    name: str
    domain: str
    type: str
    aud: str = ""
    session_duration: str = ""
    auto_redirect_to_identity: bool = False


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class CloudflareEdgeAdapter:
    """Cloudflare Zero Trust + DNS + Access edge control surface.

    Construct via :func:`get_cloudflare_adapter` for the singleton, or
    directly with a custom :class:`aqp.cloudflare.client.CloudflareClient`
    in tests.
    """

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client

    def _resolve_client(self):
        if self._client is not None:
            return self._client
        try:
            from aqp.cloudflare.client import get_cloudflare_client

            return get_cloudflare_client()
        except RuntimeError as exc:
            raise CloudflareAdapterUnavailable(str(exc)) from exc

    # ---- Health -----------------------------------------------------

    def health(self) -> dict[str, Any]:
        try:
            client = self._resolve_client()
            verify = client.sdk.user.tokens.verify()
            return {
                "status": "ok",
                "account_id": client.account_id,
                "token_id": getattr(verify, "id", None),
                "token_status": getattr(verify, "status", None),
            }
        except CloudflareAdapterUnavailable as exc:
            return {"status": "unavailable", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"status": "degraded", "error": str(exc)}

    # ---- Tunnels ----------------------------------------------------

    def list_tunnels(self, *, name: str | None = None) -> list[TunnelSummary]:
        client = self._resolve_client()
        try:
            kwargs: dict[str, Any] = {"account_id": client.account_id}
            if name:
                kwargs["name"] = name
            page = client.sdk.zero_trust.tunnels.list(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(f"list_tunnels failed: {exc}") from exc
        return [_to_tunnel_summary(t) for t in _iter_page(page)]

    def create_tunnel(
        self,
        *,
        name: str,
        config_src: str = "cloudflare",
    ) -> TunnelSummary:
        client = self._resolve_client()
        try:
            created = client.sdk.zero_trust.tunnels.create(
                account_id=client.account_id,
                name=name,
                config_src=config_src,
            )
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(f"create_tunnel failed: {exc}") from exc
        return _to_tunnel_summary(created)

    def delete_tunnel(self, *, tunnel_id: str) -> dict[str, Any]:
        client = self._resolve_client()
        try:
            client.sdk.zero_trust.tunnels.delete(
                tunnel_id=tunnel_id, account_id=client.account_id
            )
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(f"delete_tunnel failed: {exc}") from exc
        return {"tunnel_id": tunnel_id, "deleted": True}

    def get_tunnel_config(self, *, tunnel_id: str) -> dict[str, Any]:
        client = self._resolve_client()
        try:
            cfg = client.sdk.zero_trust.tunnels.cloudflared.configurations.get(
                tunnel_id=tunnel_id, account_id=client.account_id
            )
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(
                f"get_tunnel_config failed: {exc}"
            ) from exc
        return getattr(cfg, "config", {}) or {}

    def put_tunnel_config(
        self,
        *,
        tunnel_id: str,
        ingress: list[dict[str, Any]],
    ) -> dict[str, Any]:
        client = self._resolve_client()
        # Cloudflare requires a catch-all entry at the end.
        normalised = list(ingress)
        if not normalised or any("service" not in entry for entry in normalised[-1:]):
            normalised.append({"service": "http_status:404"})
        try:
            client.sdk.zero_trust.tunnels.cloudflared.configurations.update(
                tunnel_id=tunnel_id,
                account_id=client.account_id,
                config={"ingress": normalised},
            )
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(
                f"put_tunnel_config failed: {exc}"
            ) from exc
        return {"tunnel_id": tunnel_id, "rules": len(normalised)}

    # ---- Access apps ------------------------------------------------

    def list_access_apps(self) -> list[AccessAppSummary]:
        client = self._resolve_client()
        try:
            page = client.sdk.zero_trust.access.applications.list(
                account_id=client.account_id
            )
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(
                f"list_access_apps failed: {exc}"
            ) from exc
        return [_to_access_app_summary(a) for a in _iter_page(page)]

    def put_access_app(self, *, payload: dict[str, Any]) -> AccessAppSummary:
        """Create-or-update an Access application from ``payload``.

        ``payload`` follows the Cloudflare API schema directly (``name``,
        ``domain``, ``type``, ``session_duration``, ``policies``, etc.).
        When the payload includes an ``id`` field the adapter calls
        ``update``; otherwise ``create``.
        """
        client = self._resolve_client()
        try:
            if "id" in payload:
                app_id = payload.pop("id")
                created = client.sdk.zero_trust.access.applications.update(
                    app_id=app_id, account_id=client.account_id, **payload
                )
            else:
                created = client.sdk.zero_trust.access.applications.create(
                    account_id=client.account_id, **payload
                )
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(f"put_access_app failed: {exc}") from exc
        return _to_access_app_summary(created)

    # ---- DNS --------------------------------------------------------

    def list_dns_records(
        self, *, zone_id: str, name: str | None = None
    ) -> list[DnsRecordSummary]:
        client = self._resolve_client()
        try:
            kwargs: dict[str, Any] = {"zone_id": zone_id}
            if name:
                kwargs["name"] = name
            page = client.sdk.dns.records.list(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(
                f"list_dns_records failed: {exc}"
            ) from exc
        return [_to_dns_summary(r) for r in _iter_page(page)]

    def put_dns_record(
        self, *, zone_id: str, payload: dict[str, Any]
    ) -> DnsRecordSummary:
        """Create-or-update a DNS record from ``payload``.

        Payload keys mirror the Cloudflare API: ``name``, ``type``,
        ``content``, ``ttl``, ``proxied``, optional ``id``.
        """
        client = self._resolve_client()
        try:
            if "id" in payload:
                rec_id = payload.pop("id")
                created = client.sdk.dns.records.update(
                    dns_record_id=rec_id, zone_id=zone_id, **payload
                )
            else:
                created = client.sdk.dns.records.create(
                    zone_id=zone_id, **payload
                )
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(
                f"put_dns_record failed: {exc}"
            ) from exc
        return _to_dns_summary(created)

    def delete_dns_record(
        self, *, zone_id: str, record_id: str
    ) -> dict[str, Any]:
        client = self._resolve_client()
        try:
            client.sdk.dns.records.delete(
                dns_record_id=record_id, zone_id=zone_id
            )
        except Exception as exc:  # noqa: BLE001
            raise CloudflareAdapterError(
                f"delete_dns_record failed: {exc}"
            ) from exc
        return {"zone_id": zone_id, "record_id": record_id, "deleted": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_page(page) -> list:
    """Walk an SDK page object or list/generator."""
    if page is None:
        return []
    if hasattr(page, "result"):
        result = getattr(page, "result", None)
        if result is not None:
            return list(result)
    try:
        return list(page)
    except TypeError:
        try:
            return list(page.iter())
        except Exception:  # noqa: BLE001
            return []


def _to_tunnel_summary(obj: Any) -> TunnelSummary:
    return TunnelSummary(
        id=str(getattr(obj, "id", "") or ""),
        name=str(getattr(obj, "name", "") or ""),
        status=str(getattr(obj, "status", "") or ""),
        config_src=str(getattr(obj, "config_src", "") or ""),
        created_at=str(getattr(obj, "created_at", "") or ""),
        deleted_at=getattr(obj, "deleted_at", None),
        connections=int(len(getattr(obj, "connections", []) or [])),
        metadata={"remote_config": getattr(obj, "remote_config", None)},
    )


def _to_dns_summary(obj: Any) -> DnsRecordSummary:
    return DnsRecordSummary(
        id=str(getattr(obj, "id", "") or ""),
        zone_id=str(getattr(obj, "zone_id", "") or ""),
        name=str(getattr(obj, "name", "") or ""),
        type=str(getattr(obj, "type", "") or ""),
        content=str(getattr(obj, "content", "") or ""),
        ttl=int(getattr(obj, "ttl", 0) or 0),
        proxied=bool(getattr(obj, "proxied", False)),
        comment=str(getattr(obj, "comment", "") or ""),
    )


def _to_access_app_summary(obj: Any) -> AccessAppSummary:
    return AccessAppSummary(
        id=str(getattr(obj, "id", "") or ""),
        name=str(getattr(obj, "name", "") or ""),
        domain=str(getattr(obj, "domain", "") or ""),
        type=str(getattr(obj, "type", "") or ""),
        aud=str(getattr(obj, "aud", "") or ""),
        session_duration=str(getattr(obj, "session_duration", "") or ""),
        auto_redirect_to_identity=bool(
            getattr(obj, "auto_redirect_to_identity", False)
        ),
    )


# ---------------------------------------------------------------------------
# Singleton + selection
# ---------------------------------------------------------------------------


_ADAPTER: CloudflareEdgeAdapter | None = None
_ADAPTER_LOCK = threading.RLock()


def get_cloudflare_adapter() -> CloudflareEdgeAdapter:
    """Return the process-wide :class:`CloudflareEdgeAdapter` singleton."""
    global _ADAPTER
    if _ADAPTER is None:
        with _ADAPTER_LOCK:
            if _ADAPTER is None:
                _ADAPTER = CloudflareEdgeAdapter()
    return _ADAPTER


def register_cloudflare_adapter(adapter: CloudflareEdgeAdapter) -> None:
    """Inject ``adapter`` (used by tests + the AQP boot wiring)."""
    global _ADAPTER
    with _ADAPTER_LOCK:
        _ADAPTER = adapter


def reset_cloudflare_adapter() -> None:
    """Drop the active adapter so the next call rebuilds."""
    global _ADAPTER
    with _ADAPTER_LOCK:
        _ADAPTER = None


__all__ = [
    "AccessAppSummary",
    "CloudflareAdapterError",
    "CloudflareAdapterUnavailable",
    "CloudflareEdgeAdapter",
    "DnsRecordSummary",
    "TunnelSummary",
    "get_cloudflare_adapter",
    "register_cloudflare_adapter",
    "reset_cloudflare_adapter",
]
