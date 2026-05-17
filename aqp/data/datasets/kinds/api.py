"""HTTP / REST :class:`BaseDataset` (Kedro ``api.APIDataset`` analogue).

All credentials resolve through
:class:`aqp.credentials.resolver.CredentialResolver` so AGENTS hard
rule 26 (no direct ``settings.<service>_*_token`` reads from service
code) holds. This is the dataset kind that the Phase 2 Airbyte builder
emits as a stub when the user toggles "AQP-native Fetcher" — the spec
becomes the seed config for an :class:`aqp.data.fetchers.Fetcher`.

Spec config schema::

    {
      "url": "https://api.example.com/v1/quotes",  # required
      "method": "GET",
      "params": {...},
      "headers": {...},
      "json_path": "data.results",                 # dot-path to records
      "auth_kind": "bearer" | "header" | "query" | "none",
      "credential_service": "iceberg",             # CredentialKey.service
      "credential_account": "rest",                # CredentialKey.account
      "auth_field": "token",                       # which CredentialResolver field
      "auth_header_name": "Authorization",         # for header auth
      "timeout_s": 30,
    }
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.data.datasets.base import BaseDataset
from aqp.data.datasets.exceptions import DatasetSaveDisabled

logger = logging.getLogger(__name__)


class APIDataset(BaseDataset):
    kind = "api"
    writable = False  # POST/PUT lives on Fetcher subclasses

    def _validate_spec(self) -> None:
        if not str(self._spec.config.get("url") or "").strip():
            raise ValueError("APIDataset requires config.url")

    @property
    def url(self) -> str:
        return str(self._spec.config["url"]).strip()

    def _resolved_auth_value(self) -> str | None:
        cfg = self._spec.config
        kind = str(cfg.get("auth_kind") or "none").lower()
        if kind == "none":
            return None
        try:
            from aqp.credentials import CredentialKey, get_resolver
        except Exception:  # noqa: BLE001
            return None
        service = str(cfg.get("credential_service") or "").strip()
        account = str(cfg.get("credential_account") or "default").strip()
        if not service:
            logger.debug(
                "APIDataset auth_kind=%s but no credential_service configured", kind
            )
            return None
        field = str(cfg.get("auth_field") or "token").strip() or "token"
        bundle = get_resolver().resolve(CredentialKey(service, account))
        value = bundle.get(field)
        if not value:
            logger.debug("APIDataset credential %s/%s missing field %s", service, account, field)
            return None
        return str(value)

    def _build_request_kwargs(self) -> dict[str, Any]:
        cfg = self._spec.config
        method = str(cfg.get("method") or "GET").upper()
        params = dict(cfg.get("params") or {})
        headers = dict(cfg.get("headers") or {})
        timeout = float(cfg.get("timeout_s") or 30.0)
        kind = str(cfg.get("auth_kind") or "none").lower()
        token = self._resolved_auth_value()
        if token:
            if kind == "bearer":
                headers.setdefault("Authorization", f"Bearer {token}")
            elif kind == "header":
                header_name = str(cfg.get("auth_header_name") or "Authorization")
                headers.setdefault(header_name, token)
            elif kind == "query":
                query_field = str(cfg.get("auth_query_field") or "token")
                params.setdefault(query_field, token)
        return {
            "method": method,
            "params": params,
            "headers": headers,
            "timeout": timeout,
        }

    def _load(self) -> Any:
        try:
            import httpx
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("httpx is required for APIDataset") from exc
        request_kwargs = self._build_request_kwargs()
        response = httpx.request(url=self.url, **request_kwargs)
        response.raise_for_status()
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            return response.text
        path = str(self._spec.config.get("json_path") or "").strip()
        if not path:
            return payload
        cursor: Any = payload
        for segment in path.split("."):
            if not segment:
                continue
            if isinstance(cursor, list):
                try:
                    cursor = cursor[int(segment)]
                except (ValueError, IndexError):
                    return None
            elif isinstance(cursor, dict):
                cursor = cursor.get(segment)
            else:
                return None
        return cursor

    def _save(self, payload: Any) -> Any:
        raise DatasetSaveDisabled(
            "APIDataset is read-only; use a Fetcher subclass for writes"
        )

    def _exists(self) -> bool:
        return True  # cheap probe is too expensive; treat as always reachable

    def _describe(self) -> dict[str, Any]:
        cfg = self._spec.config
        return {
            "url": self.url,
            "method": str(cfg.get("method") or "GET").upper(),
            "auth_kind": str(cfg.get("auth_kind") or "none").lower(),
            "credential_service": cfg.get("credential_service"),
            "load_mode": "api",
        }


__all__ = ["APIDataset"]
