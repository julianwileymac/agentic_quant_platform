"""Celery beat task: nightly ``rl_ledger`` → S3 export for audit retention.

Reg SCI 17 CFR § 242.1005(b)(2) requires records kept "for a period
of not less than five years"; MiFID II Article 25 MiFIR (ESMA) says
"5 years minimum, up to 7". We default to 7-year retention via S3
object-lock applied at upload time.

Phase 0 ships the skeleton; Phase 6 wires the actual S3 lifecycle
policy + cassette-pinning surface.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def export_ledger_window(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    bucket: str | None = None,
    prefix: str = "aqp/rl_ledger",
) -> dict[str, Any]:
    """Export the (``since``, ``until``] window of the ``rl_ledger``."""
    until = until or datetime.utcnow()
    since = since or (until - timedelta(days=1))

    try:
        from aqp.config import settings

        bucket = bucket or getattr(settings, "ratelimit_ledger_export_bucket", None)
    except Exception:  # noqa: BLE001
        pass

    if not bucket:
        logger.info("rl_ledger export skipped: no bucket configured")
        return {"exported": 0, "bucket": None, "since": since, "until": until}

    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitLedger

    with get_session() as session:
        rows = (
            session.query(RateLimitLedger)
            .filter(
                RateLimitLedger.ts > since,
                RateLimitLedger.ts <= until,
            )
            .order_by(RateLimitLedger.ts.asc())
            .all()
        )

    exported = 0
    try:
        import io
        import json

        import boto3  # type: ignore[import-not-found]

        s3 = boto3.client("s3")
        buffer = io.BytesIO()
        for row in rows:
            buffer.write(
                json.dumps(
                    {
                        "id": int(row.id),
                        "ts": row.ts.isoformat(),
                        "service": row.service,
                        "key_id": row.key_id,
                        "tokens_consumed": int(row.tokens_consumed),
                        "decision": row.decision,
                        "actor_kind": row.actor_kind,
                        "owner_user_id": row.owner_user_id,
                        "workspace_id": row.workspace_id,
                        "meta": row.meta or {},
                    },
                    default=str,
                ).encode("utf-8")
            )
            buffer.write(b"\n")
            exported += 1
        key = f"{prefix}/{until.strftime('%Y/%m/%d')}/window.jsonl"
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=buffer.getvalue(),
            ObjectLockMode="COMPLIANCE",
            ObjectLockRetainUntilDate=until + timedelta(days=365 * 7),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("rl_ledger export failed: %s", exc)
        return {"exported": 0, "bucket": bucket, "error": str(exc)}
    logger.info("rl_ledger export OK: %s row(s) -> s3://%s/%s", exported, bucket, key)
    return {"exported": exported, "bucket": bucket, "key": key}


__all__ = ["export_ledger_window"]
