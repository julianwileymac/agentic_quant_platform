"""Redis-backed global kill switch.

When engaged, every code path that routes orders reads this key and halts.
The Meta-Agent is the only authorised principal to flip it.
"""
from __future__ import annotations

import logging

from aqp.config import settings

logger = logging.getLogger(__name__)


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def engage(reason: str = "manual") -> None:
    client = _redis()
    client.set(settings.risk_kill_switch_key, reason)
    client.publish("aqp:kill_switch:engaged", reason)
    logger.warning("KILL SWITCH ENGAGED: %s", reason)


def release() -> None:
    client = _redis()
    client.delete(settings.risk_kill_switch_key)
    client.publish("aqp:kill_switch:released", "ok")
    logger.warning("KILL SWITCH RELEASED")


def is_engaged() -> bool:
    try:
        client = _redis()
        return client.exists(settings.risk_kill_switch_key) > 0
    except Exception:
        return False


def status() -> dict:
    try:
        client = _redis()
        reason = client.get(settings.risk_kill_switch_key)
        return {"engaged": bool(reason), "reason": reason}
    except Exception as e:
        return {"engaged": False, "error": str(e)}
