"""Parsing helpers for Alpha Vantage payloads."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd


_DIGIT_PREFIX = re.compile(r"^\d+[. ]+")


def snake_key(key: str) -> str:
    cleaned = _DIGIT_PREFIX.sub("", str(key)).strip()
    cleaned = cleaned.replace("%", "percent")
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", cleaned)
    cleaned = re.sub(r"(?<!^)(?=[A-Z])", "_", cleaned)
    return cleaned.strip("_").lower()


def normalize_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    return {snake_key(k): v for k, v in payload.items()}


def to_epoch_ns(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        ts = pd.Timestamp(value)
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return int(ts.value)
    except Exception:
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["normalize_mapping", "snake_key", "to_epoch_ns", "utc_now_iso"]
