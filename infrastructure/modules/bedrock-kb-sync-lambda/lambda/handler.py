"""Bedrock Knowledge Base lazy re-ingestion Lambda.

Triggered by EventBridge whenever an object lands in the KB source
bucket. Calls ``bedrock-agent:StartIngestionJob`` for the configured
KB + data source so the new (or updated) document gets indexed
within the KB's poll cadence.

Idempotent: duplicate events for the same KB are coalesced by AWS at
the KB-side (only one ingestion job runs per KB at any time;
subsequent calls return the existing in-flight job ARN). We log + swallow
the ``ConflictException`` so retries don't surface as failures.

Per the management-engine credential-safety rule, the handler MUST NOT
log object keys that may carry tenant identifiers verbatim. We hash
the key + log the hash + the byte size only.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


KB_ID = os.environ.get("KB_ID", "").strip()
DATA_SOURCE_ID = os.environ.get("DATA_SOURCE_ID", "").strip()
AQP_ENV = os.environ.get("AQP_ENV", "dev").strip()


def _redact(key: str) -> str:
    """Hash-then-truncate an object key so we don't log tenant ids."""
    if not key:
        return ""
    digest = hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()
    return digest[:16]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge ``Object Created`` invocation handler.

    Event shape (per EventBridge S3 detail-type schema):

    .. code-block:: json

        {
          "source": "aws.s3",
          "detail-type": "Object Created",
          "detail": {
            "bucket": {"name": "..."},
            "object": {"key": "...", "size": 1234}
          }
        }
    """
    if not KB_ID or not DATA_SOURCE_ID:
        logger.error("KB_ID / DATA_SOURCE_ID env vars are unset; refusing to start")
        return {"started": False, "reason": "config_missing"}

    detail = event.get("detail") or {}
    bucket = (detail.get("bucket") or {}).get("name") or ""
    obj = detail.get("object") or {}
    key = obj.get("key") or ""
    size = obj.get("size") or 0
    logger.info(
        "kb_sync invocation env=%s bucket=%s key_hash=%s size_bytes=%s",
        AQP_ENV,
        bucket,
        _redact(key),
        size,
    )

    client = boto3.client("bedrock-agent")
    try:
        response = client.start_ingestion_job(
            knowledgeBaseId=KB_ID,
            dataSourceId=DATA_SOURCE_ID,
            description=f"aqp-kb-sync env={AQP_ENV} key_hash={_redact(key)} size={size}",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code") or ""
        if code in ("ConflictException", "ThrottlingException"):
            logger.info(
                "kb_sync coalesced — ingestion already in flight for KB=%s (%s)",
                KB_ID,
                code,
            )
            return {"started": False, "coalesced": True, "code": code}
        logger.exception("start_ingestion_job failed code=%s", code)
        raise
    except Exception:
        logger.exception("start_ingestion_job raised unexpectedly")
        raise

    job = response.get("ingestionJob") or {}
    job_id = job.get("ingestionJobId") or ""
    status = job.get("status") or ""
    logger.info("kb_sync started job_id=%s status=%s", job_id, status)
    return {
        "started": True,
        "ingestion_job_id": job_id,
        "status": status,
    }
