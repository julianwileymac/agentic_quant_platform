"""Celery beat task: nightly ``security_audit_events`` + ``audit_log`` -> S3 WORM.

Per FINRA Rule 4511 + SEC Rule 17a-4(f)(2)(i)(B) electronic records
must be retained for 6 years (first 2 readily accessible) on
non-rewriteable / non-erasable media. We default to a 7-year
retention so the WORM tier carries one year of safety margin
beyond the regulatory minimum. Implementation pattern is the same
as :func:`aqp_ratelimit.tasks.ledger_export.export_ledger_window`
that already ships for the rate-limit ledger.

Bucket layout::

    s3://aqp-audit-archive-${ACCOUNT_ID}/security_audit_events/
        year=2026/month=05/day=24/window-2026-05-24T02-00-00Z.jsonl
    s3://aqp-audit-archive-${ACCOUNT_ID}/audit_log/
        year=2026/month=05/day=24/window-2026-05-24T02-00-00Z.jsonl

Object Lock = Compliance mode + 7-year retention; KMS encryption
via the per-account customer-managed key. Bucket lifecycle moves
> 90d -> Glacier IR; > 365d -> Deep Archive.
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _serialize_security_audit_event(row: Any) -> dict[str, Any]:
    """Turn a `SecurityAuditEvent` ORM row into a JSON-safe dict.

    Mirrors the audit ledger contract: append-only, no fields
    elided, never includes secret material (the model's
    `__setattr__` guard guarantees that).
    """
    return {
        "id": str(row.id),
        "user_id": str(row.user_id) if row.user_id else None,
        "organization_id": str(row.organization_id) if row.organization_id else None,
        "workspace_id": str(row.workspace_id) if row.workspace_id else None,
        "event_type": row.event_type,
        "event_category": row.event_category,
        "severity": row.severity,
        "source": row.source,
        "ip": row.ip,
        "user_agent": row.user_agent,
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "connection": row.connection,
        "request_id": row.request_id,
        "details": row.details or {},
        "created_at": _iso(row.created_at),
    }


def _serialize_audit_log(row: Any) -> dict[str, Any]:
    """Turn a hash-chained `AuditLog` ORM row into a JSON-safe dict.

    The hash chain is preserved end-to-end so an auditor can verify
    the chain server-side from the WORM archive alone.
    """
    return {
        "id": int(row.id),
        "ts": _iso(row.ts),
        "event_category": row.event_category,
        "event_type": row.event_type,
        "actor_kind": row.actor_kind,
        "agent_subject": row.agent_subject,
        "on_behalf_of_user_id": str(row.on_behalf_of_user_id) if row.on_behalf_of_user_id else None,
        "tool_id": row.tool_id,
        "approval_id": str(row.approval_id) if row.approval_id else None,
        "template_id": str(row.template_id) if row.template_id else None,
        "connection_id": str(row.connection_id) if row.connection_id else None,
        "request_id": row.request_id,
        "details": row.details or {},
        "prev_hash": row.prev_hash.hex() if row.prev_hash else None,
        "hash": row.hash.hex() if row.hash else None,
    }


def _put_worm(
    s3_client: Any,
    *,
    bucket: str,
    key: str,
    body: bytes,
    retention_until: datetime,
) -> None:
    """Upload bytes to S3 with Object Lock = COMPLIANCE."""
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ObjectLockMode="COMPLIANCE",
        ObjectLockRetainUntilDate=retention_until,
        ServerSideEncryption="aws:kms",
    )


def _serialize_window(rows: Iterable[Any], serializer) -> bytes:
    buffer = io.BytesIO()
    for row in rows:
        buffer.write(json.dumps(serializer(row), default=str).encode("utf-8"))
        buffer.write(b"\n")
    return buffer.getvalue()


def export_audit_log_window(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    bucket: str | None = None,
    retention_years: int = 7,
) -> dict[str, Any]:
    """Export the (since, until] window of security_audit_events + audit_log.

    Returns a JSON-safe summary that the Celery beat surface logs:
    counts per ledger, S3 keys, retention timestamps. Never raises
    — failures land in the summary so the operator alerting (set up
    via the kube-prometheus-stack) can fire on anomalous zero-row
    days.
    """
    until = until or datetime.now(timezone.utc)
    since = since or (until - timedelta(days=1))

    try:
        from aqp.config import settings

        bucket = bucket or getattr(settings, "audit_archive_bucket", None)
    except Exception:  # noqa: BLE001
        pass

    if not bucket:
        logger.info("audit-log export skipped: no audit_archive_bucket configured")
        return {"exported_security": 0, "exported_audit_log": 0, "bucket": None}

    summary: dict[str, Any] = {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "bucket": bucket,
        "exported_security": 0,
        "exported_audit_log": 0,
    }

    try:
        import boto3  # type: ignore[import-not-found]

        from aqp.persistence.db import get_session
        from aqp.persistence.models_audit import SecurityAuditEvent
        from aqp.persistence.models_ratelimit import AuditLog
    except ImportError as exc:
        logger.warning("audit-log export missing deps: %s", exc)
        summary["error"] = f"missing dep: {exc}"
        return summary

    s3 = boto3.client("s3")
    retention_until = until + timedelta(days=365 * retention_years)

    with get_session() as session:
        sae_rows = (
            session.query(SecurityAuditEvent)
            .filter(
                SecurityAuditEvent.created_at > since,
                SecurityAuditEvent.created_at <= until,
            )
            .order_by(SecurityAuditEvent.created_at.asc())
            .all()
        )
        al_rows = (
            session.query(AuditLog)
            .filter(AuditLog.ts > since, AuditLog.ts <= until)
            .order_by(AuditLog.ts.asc())
            .all()
        )

    if sae_rows:
        body = _serialize_window(sae_rows, _serialize_security_audit_event)
        key = (
            f"security_audit_events/year={until.strftime('%Y')}/"
            f"month={until.strftime('%m')}/day={until.strftime('%d')}/"
            f"window-{until.strftime('%Y-%m-%dT%H-%M-%SZ')}.jsonl"
        )
        try:
            _put_worm(s3, bucket=bucket, key=key, body=body, retention_until=retention_until)
            summary["exported_security"] = len(sae_rows)
            summary["security_key"] = key
        except Exception as exc:  # noqa: BLE001
            logger.warning("security_audit_events export failed: %s", exc)
            summary["security_error"] = str(exc)

    if al_rows:
        body = _serialize_window(al_rows, _serialize_audit_log)
        key = (
            f"audit_log/year={until.strftime('%Y')}/"
            f"month={until.strftime('%m')}/day={until.strftime('%d')}/"
            f"window-{until.strftime('%Y-%m-%dT%H-%M-%SZ')}.jsonl"
        )
        try:
            _put_worm(s3, bucket=bucket, key=key, body=body, retention_until=retention_until)
            summary["exported_audit_log"] = len(al_rows)
            summary["audit_log_key"] = key
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_log export failed: %s", exc)
            summary["audit_log_error"] = str(exc)

    logger.info(
        "audit-log export: security=%s audit_log=%s -> s3://%s",
        summary["exported_security"],
        summary["exported_audit_log"],
        bucket,
    )
    return summary


# ---------------------------------------------------------------------------
# Celery task wrapper — registered on the beat schedule for 02:00 UTC daily.
# ---------------------------------------------------------------------------


try:  # pragma: no cover — celery is optional in unit-test contexts
    from aqp.tasks.celery_app import celery_app

    @celery_app.task(name="aqp.tasks.audit_log_export.export_nightly")
    def export_nightly_task() -> dict[str, Any]:  # type: ignore[misc]
        """Beat-scheduled wrapper around :func:`export_audit_log_window`."""
        return export_audit_log_window()
except Exception:  # noqa: BLE001
    pass


__all__ = ["export_audit_log_window"]
