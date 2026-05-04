"""Idempotent Polaris/Iceberg bootstrap for the local AQP stack.

Creates the catalog (warehouse), a service principal, the principal/catalog
roles, and the catalog grant required for Trino + PyIceberg + AQP itself
to operate against Polaris. Persists the captured principal credentials so
re-runs reuse them and so api/worker can mount them on next start.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from aqp.config import settings
from aqp.observability import get_tracer
from aqp.services.polaris_client import (
    PolarisClient,
    PolarisClientConfig,
    PolarisClientError,
    default_polaris_config,
)

logger = logging.getLogger(__name__)
_tracer = get_tracer("aqp.services.iceberg_bootstrap")

PRINCIPAL_CREDENTIAL_FILENAME = "polaris-principal.json"


@dataclass
class BootstrapStep:
    name: str
    status: str  # "ok" | "created" | "exists" | "skipped" | "error"
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class BootstrapReport:
    catalog: str
    principal: str
    principal_role: str
    catalog_role: str
    privilege: str
    started_at: float
    finished_at: float
    duration_seconds: float
    success: bool
    bootstrap_required: bool
    steps: list[BootstrapStep]
    credentials_file: str | None = None
    credentials_persisted: bool = False
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["steps"] = [asdict(step) for step in self.steps]
        return out


def _bootstrap_state_dir() -> Path:
    base = Path(settings.bootstrap_state_dir).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def credentials_file() -> Path:
    return _bootstrap_state_dir() / PRINCIPAL_CREDENTIAL_FILENAME


def load_persisted_credentials() -> dict[str, Any] | None:
    """Return persisted Polaris principal credentials if available."""
    path = credentials_file()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read polaris principal credentials at %s: %s", path, exc)
        return None


def persist_principal_credentials(payload: dict[str, Any]) -> Path:
    """Persist Polaris principal credentials to disk with restrictive perms."""
    path = credentials_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    with contextlib.suppress(Exception):  # pragma: no cover - chmod unsupported on Windows
        os.chmod(path, 0o600)
    return path


def _extract_credentials(create_payload: dict[str, Any]) -> dict[str, str] | None:
    """Pull the new principal credentials out of a Polaris create response."""
    creds = create_payload.get("credentials") if isinstance(create_payload, dict) else None
    if not isinstance(creds, dict):
        creds = create_payload.get("credential") if isinstance(create_payload, dict) else None
    if not isinstance(creds, dict):
        return None
    client_id = str(creds.get("clientId") or creds.get("client_id") or "")
    client_secret = str(
        creds.get("clientSecret") or creds.get("client_secret") or creds.get("secret") or ""
    )
    if not client_id or not client_secret:
        return None
    return {"client_id": client_id, "client_secret": client_secret}


def _polaris_storage_kwargs() -> dict[str, Any]:
    if (settings.iceberg_catalog_storage_type or "FILE").upper() != "S3":
        return {}
    return {
        "endpoint": settings.s3_endpoint_url or "http://minio:9000",
        "region": settings.s3_region or "us-east-1",
        "access_key": settings.s3_access_key or "",
        "secret_key": settings.s3_secret_key or "",
        "path_style_access": True,
    }


class IcebergBootstrapManager:
    """High-level orchestration for the Polaris bootstrap sequence."""

    def __init__(
        self,
        client: PolarisClient | None = None,
        *,
        config: PolarisClientConfig | None = None,
        catalog_name: str | None = None,
        principal_name: str | None = None,
        principal_role: str | None = None,
        catalog_role: str | None = None,
        privilege: str | None = None,
        default_base_location: str | None = None,
        storage_type: str | None = None,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._config = config or default_polaris_config()
        self.catalog_name = catalog_name or settings.iceberg_catalog_warehouse_name
        self.principal_name = principal_name or settings.iceberg_principal_name
        self.principal_role = principal_role or settings.iceberg_principal_role
        self.catalog_role = catalog_role or settings.iceberg_catalog_role
        self.privilege = privilege or settings.iceberg_catalog_privilege
        self.default_base_location = (
            default_base_location or settings.iceberg_default_base_location
        )
        self.storage_type = (storage_type or settings.iceberg_catalog_storage_type or "FILE").upper()

    def _client_handle(self) -> PolarisClient:
        if self._client is None:
            self._client = PolarisClient(self._config)
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None

    def __enter__(self) -> IcebergBootstrapManager:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return a structured snapshot of the bootstrap state.

        Each component is checked independently so the UI can show
        partial progress when only some steps have completed.
        """
        client = self._client_handle()
        result: dict[str, Any] = {
            "catalog": self.catalog_name,
            "principal": self.principal_name,
            "principal_role": self.principal_role,
            "catalog_role": self.catalog_role,
            "privilege": self.privilege,
            "polaris_reachable": False,
            "catalog_present": False,
            "principal_present": False,
            "principal_role_present": False,
            "catalog_role_present": False,
            "credentials_persisted": credentials_file().exists(),
            "credentials_file": str(credentials_file()),
            "error": None,
        }
        try:
            client.oauth_token(force=True)
            result["polaris_reachable"] = True
        except PolarisClientError as exc:
            result["error"] = str(exc)
            return result
        try:
            result["catalog_present"] = bool(client.get_catalog(self.catalog_name))
            result["principal_present"] = bool(client.get_principal(self.principal_name))
            result["principal_role_present"] = bool(
                client.get_principal_role(self.principal_role)
            )
            result["catalog_role_present"] = bool(
                client.get_catalog_role(catalog=self.catalog_name, role=self.catalog_role)
                if result["catalog_present"]
                else None
            )
        except PolarisClientError as exc:
            result["error"] = str(exc)
        return result

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap(self) -> BootstrapReport:
        """Run all bootstrap steps idempotently and return a structured report."""
        started = time.monotonic()
        steps: list[BootstrapStep] = []
        success = True
        last_error: str | None = None
        credentials_persisted = False
        credentials_path: str | None = None
        client = self._client_handle()

        with _tracer.start_as_current_span("iceberg.bootstrap") as span:
            span.set_attribute("polaris.catalog", self.catalog_name)
            span.set_attribute("polaris.principal", self.principal_name)
            try:
                client.oauth_token(force=True)
                steps.append(BootstrapStep(name="oauth", status="ok", detail="token acquired"))
            except PolarisClientError as exc:
                steps.append(BootstrapStep(name="oauth", status="error", detail=str(exc)))
                return BootstrapReport(
                    catalog=self.catalog_name,
                    principal=self.principal_name,
                    principal_role=self.principal_role,
                    catalog_role=self.catalog_role,
                    privilege=self.privilege,
                    started_at=started,
                    finished_at=time.monotonic(),
                    duration_seconds=round(time.monotonic() - started, 4),
                    success=False,
                    bootstrap_required=True,
                    steps=steps,
                    last_error=str(exc),
                )

            steps.append(self._ensure_catalog(client))
            principal_step, principal_payload = self._ensure_principal(client)
            steps.append(principal_step)
            if principal_payload is not None:
                creds = _extract_credentials(principal_payload)
                if creds:
                    creds_payload = {
                        "principal": self.principal_name,
                        **creds,
                    }
                    path = persist_principal_credentials(creds_payload)
                    credentials_path = str(path)
                    credentials_persisted = True
                    steps.append(
                        BootstrapStep(
                            name="persist_principal_credentials",
                            status="ok",
                            detail=str(path),
                            payload={"client_id": creds["client_id"]},
                        )
                    )
            existing_creds = load_persisted_credentials()
            if not credentials_persisted and existing_creds:
                credentials_path = str(credentials_file())
                credentials_persisted = True
            steps.append(self._ensure_principal_role(client))
            steps.append(self._assign_principal_role(client))
            steps.append(self._ensure_catalog_role(client))
            steps.append(self._assign_catalog_role(client))
            steps.append(self._grant_catalog_privilege(client))

        for step in steps:
            if step.status == "error":
                success = False
                last_error = last_error or step.detail
        finished = time.monotonic()
        report = BootstrapReport(
            catalog=self.catalog_name,
            principal=self.principal_name,
            principal_role=self.principal_role,
            catalog_role=self.catalog_role,
            privilege=self.privilege,
            started_at=started,
            finished_at=finished,
            duration_seconds=round(finished - started, 4),
            success=success,
            bootstrap_required=not success,
            steps=steps,
            credentials_file=credentials_path,
            credentials_persisted=credentials_persisted,
            last_error=last_error,
        )
        if success:
            logger.info(
                "Polaris bootstrap completed: catalog=%s principal=%s steps=%d",
                self.catalog_name,
                self.principal_name,
                len(steps),
            )
        else:
            logger.warning(
                "Polaris bootstrap failed (last_error=%s) after %d steps",
                last_error,
                len(steps),
            )
        return report

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _ensure_catalog(self, client: PolarisClient) -> BootstrapStep:
        try:
            existing = client.get_catalog(self.catalog_name)
            if existing:
                return BootstrapStep(
                    name="ensure_catalog",
                    status="exists",
                    detail=self.catalog_name,
                    payload={"catalog": existing},
                )
            payload = client.create_catalog(
                self.catalog_name,
                default_base_location=self.default_base_location,
                storage_type=self.storage_type,
                s3=_polaris_storage_kwargs(),
            )
            return BootstrapStep(
                name="ensure_catalog",
                status="created",
                detail=self.catalog_name,
                payload={"catalog": payload},
            )
        except PolarisClientError as exc:
            return BootstrapStep(name="ensure_catalog", status="error", detail=str(exc))

    def _ensure_principal(
        self, client: PolarisClient
    ) -> tuple[BootstrapStep, dict[str, Any] | None]:
        try:
            existing = client.get_principal(self.principal_name)
            if existing:
                return (
                    BootstrapStep(
                        name="ensure_principal",
                        status="exists",
                        detail=self.principal_name,
                        payload={"principal": existing},
                    ),
                    None,
                )
            payload = client.create_principal(self.principal_name)
            return (
                BootstrapStep(
                    name="ensure_principal",
                    status="created",
                    detail=self.principal_name,
                    payload={"principal": payload},
                ),
                payload,
            )
        except PolarisClientError as exc:
            return (
                BootstrapStep(name="ensure_principal", status="error", detail=str(exc)),
                None,
            )

    def _ensure_principal_role(self, client: PolarisClient) -> BootstrapStep:
        try:
            existing = client.get_principal_role(self.principal_role)
            if existing:
                return BootstrapStep(
                    name="ensure_principal_role",
                    status="exists",
                    detail=self.principal_role,
                )
            payload = client.create_principal_role(self.principal_role)
            return BootstrapStep(
                name="ensure_principal_role",
                status="created",
                detail=self.principal_role,
                payload={"principal_role": payload},
            )
        except PolarisClientError as exc:
            return BootstrapStep(
                name="ensure_principal_role",
                status="error",
                detail=str(exc),
            )

    def _assign_principal_role(self, client: PolarisClient) -> BootstrapStep:
        try:
            client.assign_principal_role(
                principal=self.principal_name,
                principal_role=self.principal_role,
            )
            return BootstrapStep(
                name="assign_principal_role",
                status="ok",
                detail=f"{self.principal_name} -> {self.principal_role}",
            )
        except PolarisClientError as exc:
            return BootstrapStep(
                name="assign_principal_role",
                status="error",
                detail=str(exc),
            )

    def _ensure_catalog_role(self, client: PolarisClient) -> BootstrapStep:
        try:
            existing = client.get_catalog_role(catalog=self.catalog_name, role=self.catalog_role)
            if existing:
                return BootstrapStep(
                    name="ensure_catalog_role",
                    status="exists",
                    detail=self.catalog_role,
                )
            payload = client.create_catalog_role(
                catalog=self.catalog_name, role=self.catalog_role
            )
            return BootstrapStep(
                name="ensure_catalog_role",
                status="created",
                detail=self.catalog_role,
                payload={"catalog_role": payload},
            )
        except PolarisClientError as exc:
            return BootstrapStep(name="ensure_catalog_role", status="error", detail=str(exc))

    def _assign_catalog_role(self, client: PolarisClient) -> BootstrapStep:
        try:
            client.assign_catalog_role(
                catalog=self.catalog_name,
                principal_role=self.principal_role,
                catalog_role=self.catalog_role,
            )
            return BootstrapStep(
                name="assign_catalog_role",
                status="ok",
                detail=f"{self.principal_role} -> {self.catalog_name}.{self.catalog_role}",
            )
        except PolarisClientError as exc:
            return BootstrapStep(name="assign_catalog_role", status="error", detail=str(exc))

    def _grant_catalog_privilege(self, client: PolarisClient) -> BootstrapStep:
        try:
            client.grant_catalog_privilege(
                catalog=self.catalog_name,
                catalog_role=self.catalog_role,
                privilege=self.privilege,
            )
            return BootstrapStep(
                name="grant_catalog_privilege",
                status="ok",
                detail=self.privilege,
            )
        except PolarisClientError as exc:
            return BootstrapStep(
                name="grant_catalog_privilege",
                status="error",
                detail=str(exc),
            )


__all__ = [
    "BootstrapReport",
    "BootstrapStep",
    "IcebergBootstrapManager",
    "credentials_file",
    "load_persisted_credentials",
    "persist_principal_credentials",
]
