"""dbt-loom S3 manifest registry sidecar (Phase 2, plan section 6).

Publishes each project's compiled ``manifest.json`` to S3 so
downstream team projects can resolve cross-project ``ref()`` calls
through dbt-loom v0.9.4. Bucket layout::

    s3://{bucket}/{env}/{project_slug}/{git_sha}/manifest.json
    s3://{bucket}/{env}/{project_slug}/manifest.json   (alias for latest)

The Phase 2 deployment runs this as a Celery beat task after every
``dbt parse`` so the manifest stays fresh; the GitHub Actions
branch-deployment workflow (Phase 3) also calls it on push.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def publish_manifest(
    *,
    project_slug: str,
    git_sha: str,
    env: str = "dev",
    manifest_path: Path | str | None = None,
    bucket: str | None = None,
    s3_client: Any | None = None,
) -> dict[str, str]:
    """Publish a single manifest.json to S3.

    Returns ``{"version_key", "latest_key"}`` so the caller can log
    the canonical S3 URIs.
    """
    if bucket is None:
        try:
            from aqp.config import settings

            bucket = getattr(settings, "dbt_loom_bucket", None) or "aqp-dbt-manifests"
        except Exception:  # noqa: BLE001
            bucket = "aqp-dbt-manifests"
    manifest_path = Path(manifest_path or "target/manifest.json")
    if not manifest_path.exists():
        logger.warning("dbt manifest not found at %s; nothing published", manifest_path)
        return {"version_key": "", "latest_key": ""}
    body = manifest_path.read_bytes()

    if s3_client is None:
        try:
            import boto3  # type: ignore[import-not-found]

            s3_client = boto3.client("s3")
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not init s3 client: %s", exc)
            return {"version_key": "", "latest_key": ""}

    version_key = f"{env}/{project_slug}/{git_sha}/manifest.json"
    latest_key = f"{env}/{project_slug}/manifest.json"
    try:
        s3_client.put_object(
            Bucket=bucket, Key=version_key, Body=body, ContentType="application/json"
        )
        s3_client.put_object(
            Bucket=bucket, Key=latest_key, Body=body, ContentType="application/json"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("manifest publish failed: %s", exc)
        return {"version_key": "", "latest_key": ""}
    logger.info(
        "dbt-loom manifest published: s3://%s/%s + s3://%s/%s",
        bucket,
        version_key,
        bucket,
        latest_key,
    )
    return {"version_key": version_key, "latest_key": latest_key}


def publish_all_known(
    *,
    git_sha: str,
    env: str = "dev",
    project_root: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Publish every known team project's manifest.

    Walks ``aqp/data/dbt/projects/*/target/manifest.json`` and
    publishes each. Used by the Celery beat task.
    """
    root = project_root or Path(__file__).resolve().parents[0] / "projects"
    out: dict[str, dict[str, str]] = {}
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        manifest = project_dir / "target" / "manifest.json"
        if not manifest.exists():
            continue
        result = publish_manifest(
            project_slug=f"aqp_dbt_{project_dir.name}",
            git_sha=git_sha,
            env=env,
            manifest_path=manifest,
        )
        out[project_dir.name] = result
    return out


__all__ = ["publish_all_known", "publish_manifest"]
