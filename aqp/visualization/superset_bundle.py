"""Superset YAML asset bundles — bulk export/import + round-trip helpers.

Superset's import/export endpoints round-trip a zip whose layout matches
its CLI-compatible `superset import-dashboards` / `superset
export-dashboards` format::

    bundle.zip
    ├── metadata.yaml
    ├── databases/<slug>.yaml
    ├── datasets/<schema>/<table>.yaml
    ├── charts/<slug>.yaml
    └── dashboards/<slug>.yaml

This module wraps the REST endpoints (``/api/v1/dashboard/export/`` and
``/api/v1/dashboard/import/``) plus a pair of helpers that can read /
write the same layout from a directory checked into the repo, so a
curated bundle can ship in version control alongside the Python sources.
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

from aqp.observability import get_tracer
from aqp.services.superset_client import SupersetClient

logger = logging.getLogger(__name__)
_TRACER = get_tracer("aqp.visualization.superset_bundle")


# ---------------------------------------------------------------------------
# REST round-trip
# ---------------------------------------------------------------------------


def export_bundle(
    client: SupersetClient,
    *,
    dashboard_ids: Iterable[int] | None = None,
) -> bytes:
    """Pull a CLI-compatible zip bundle from Superset.

    When ``dashboard_ids`` is None we export every dashboard the
    authenticated user can see; otherwise we filter via Rison-encoded
    ``q={!(...)}``.
    """

    with _TRACER.start_as_current_span("superset.bundle.export") as span:
        ids: list[int] = list(dashboard_ids) if dashboard_ids is not None else _list_dashboard_ids(client)
        span.set_attribute("superset.bundle.dashboard_count", len(ids))
        if not ids:
            raise RuntimeError("no dashboards available for export — run /visualizations/superset/sync first")

        # Superset uses Rison-encoded array for the q param.
        q = "!(" + ",".join(str(int(i)) for i in ids) + ")"
        url = f"{client.base_url}/api/v1/dashboard/export/?q={q}"
        token = client.auth.access_token
        # Direct httpx call so we can keep the response body as raw bytes;
        # SupersetClient._request decodes JSON.
        response = client._client.get(  # noqa: SLF001 — internal singleton client
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/zip"},
        )
        response.raise_for_status()
        body = response.content
        span.set_attribute("superset.bundle.bytes", len(body))
        return body


def import_bundle(
    client: SupersetClient,
    zip_bytes: bytes,
    *,
    passwords: dict[str, str] | None = None,
    overwrite: bool = True,
    filename: str = "aqp_bundle.zip",
) -> dict[str, Any]:
    """Push a CLI-compatible zip bundle to Superset.

    ``passwords`` maps the YAML database slug → SQLAlchemy connection
    password (Superset strips them on export and demands them back on
    import for any database that uses one). ``overwrite=True`` replaces
    any pre-existing assets with the same slug/uuid.
    """

    with _TRACER.start_as_current_span("superset.bundle.import") as span:
        span.set_attribute("superset.bundle.bytes", len(zip_bytes))
        span.set_attribute("superset.bundle.overwrite", overwrite)
        url = f"{client.base_url}/api/v1/dashboard/import/"
        # CSRF-protected mutating endpoint; force the client to mint one.
        csrf = client.csrf_token()
        files = {"formData": (filename, zip_bytes, "application/zip")}
        data: dict[str, Any] = {"overwrite": "true" if overwrite else "false"}
        if passwords:
            data["passwords"] = json.dumps(passwords)
        response = client._client.post(  # noqa: SLF001
            url,
            headers={
                "Authorization": f"Bearer {client.auth.access_token}",
                "X-CSRFToken": csrf,
                "Referer": client.base_url,
            },
            files=files,
            data=data,
        )
        if response.status_code >= 400:
            logger.warning("Superset import-bundle returned %s: %s", response.status_code, response.text)
            response.raise_for_status()
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError):
            payload = {"text": response.text}
        return payload if isinstance(payload, dict) else {"result": payload}


def _list_dashboard_ids(client: SupersetClient) -> list[int]:
    rows = client.list_dashboards()
    return [int(row["id"]) for row in rows if row.get("id") is not None]


# ---------------------------------------------------------------------------
# Filesystem round-trip
# ---------------------------------------------------------------------------


def write_bundle_dir(zip_bytes: bytes, target_dir: Path) -> Path:
    """Unzip ``zip_bytes`` into ``target_dir``, overwriting in place.

    Returns the resolved target directory.
    """

    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Strip the top-level "<bundle>/" prefix Superset always wraps things
        # in so the on-disk layout matches the documented CLI format.
        names = zf.namelist()
        prefix = ""
        if names:
            head = names[0].split("/", 1)[0]
            if all(name.startswith(head + "/") for name in names if name):
                prefix = head + "/"
        for member in zf.infolist():
            if member.is_dir():
                continue
            relative = member.filename[len(prefix) :] if prefix else member.filename
            if not relative:
                continue
            dest = target_dir / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as source, dest.open("wb") as out:
                out.write(source.read())
    return target_dir


def read_bundle_dir(source_dir: Path, *, archive_name: str = "aqp_bundle") -> bytes:
    """Zip a directory previously produced by :func:`write_bundle_dir`.

    The archive members are written under a single top-level
    ``<archive_name>/`` prefix so Superset's importer accepts them.
    """

    source_dir = Path(source_dir).resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"bundle directory not found: {source_dir}")
    if not (source_dir / "metadata.yaml").exists():
        raise FileNotFoundError(
            f"bundle directory missing metadata.yaml: {source_dir} — was it produced by Superset export?"
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                arcname = f"{archive_name}/{path.relative_to(source_dir).as_posix()}"
                zf.write(path, arcname)
    return buffer.getvalue()


def import_bundle_from_dir(
    client: SupersetClient,
    source_dir: Path,
    *,
    passwords: dict[str, str] | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Convenience wrapper: zip the directory, then push to Superset."""

    zip_bytes = read_bundle_dir(source_dir, archive_name=Path(source_dir).name)
    return import_bundle(client, zip_bytes, passwords=passwords, overwrite=overwrite,
                         filename=f"{Path(source_dir).name}.zip")


def export_bundle_to_dir(
    client: SupersetClient,
    target_dir: Path,
    *,
    dashboard_ids: Iterable[int] | None = None,
) -> Path:
    """Convenience wrapper: pull a fresh bundle from Superset and unzip it on disk."""

    zip_bytes = export_bundle(client, dashboard_ids=dashboard_ids)
    return write_bundle_dir(zip_bytes, target_dir)


__all__ = [
    "export_bundle",
    "export_bundle_to_dir",
    "import_bundle",
    "import_bundle_from_dir",
    "read_bundle_dir",
    "write_bundle_dir",
]


# Make httpx import explicit (kept for type-checkers that flag the unused
# import otherwise; the underlying SupersetClient already pulls it in).
_ = httpx
