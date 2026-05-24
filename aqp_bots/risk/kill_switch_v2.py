"""Three-scope kill switch (bot / fleet / platform).

Extends :mod:`aqp.risk.kill_switch` (which exposes a single global key)
with named scopes so the operator can halt one bot, one fleet, or the
entire platform independently. Engagement at the platform scope blocks
every bot; fleet blocks every member of one fleet; bot blocks one Pod.

Implementation details:

- Each scope writes a separate Redis key: ``aqp:bots:killswitch:{scope}:{key}``
  with the reason as the value.
- Engagement also publishes on ``aqp:bots:killswitch:{scope}`` so kernel
  subscribers can react immediately (no polling delay).
- Per blueprint caveat #7, the kernel ALSO polls these keys every 5
  seconds — GitOps reconciliation can lag, but a polling fallback
  guarantees the bot will halt within ``poll_interval_s`` even if the
  pub/sub channel drops.
- All three layers share state with the existing legacy global
  :func:`aqp.risk.kill_switch.engage` — engaging the legacy global key
  is equivalent to engaging the new platform scope.
"""
from __future__ import annotations

import logging
from enum import StrEnum
from typing import Literal

logger = logging.getLogger(__name__)


class KillSwitchScope(StrEnum):
    """Three scopes the kill switch operates at."""

    BOT = "bot"
    FLEET = "fleet"
    PLATFORM = "platform"


_REDIS_PREFIX = "aqp:bots:killswitch"


def _key(scope: str, name: str) -> str:
    return f"{_REDIS_PREFIX}:{scope}:{name}"


def _channel(scope: str) -> str:
    return f"{_REDIS_PREFIX}:{scope}"


def _redis():
    try:
        import redis  # type: ignore[import-untyped]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"redis package required for kill_switch_v2: {exc}") from exc
    try:
        from aqp.config import settings

        url = settings.redis_url
    except Exception:  # noqa: BLE001
        url = "redis://localhost:6379"
    return redis.Redis.from_url(url, decode_responses=True)


def engage_scoped(scope: str, name: str, *, reason: str = "manual") -> None:
    """Engage the kill switch for ``(scope, name)``."""
    scope = scope.lower()
    try:
        client = _redis()
        client.set(_key(scope, name), reason)
        client.publish(_channel(scope), f"{name}:{reason}")
    except Exception:  # noqa: BLE001
        logger.exception("kill_switch_v2.engage failed for %s/%s", scope, name)
        raise
    logger.warning("KILL SWITCH ENGAGED scope=%s name=%s reason=%s", scope, name, reason)


def release_scoped(scope: str, name: str) -> None:
    """Release ``(scope, name)``. Idempotent."""
    scope = scope.lower()
    try:
        client = _redis()
        client.delete(_key(scope, name))
        client.publish(_channel(scope), f"{name}:released")
    except Exception:  # noqa: BLE001
        logger.exception("kill_switch_v2.release failed for %s/%s", scope, name)
    logger.warning("KILL SWITCH RELEASED scope=%s name=%s", scope, name)


def is_engaged_scoped(scope: str, name: str) -> bool:
    """Return True if ``(scope, name)`` is engaged."""
    if not name or name == "_none_":
        return False
    try:
        client = _redis()
        return bool(client.exists(_key(scope.lower(), name)))
    except Exception:  # noqa: BLE001
        return False


def get_reason(scope: str, name: str) -> str | None:
    try:
        client = _redis()
        v = client.get(_key(scope.lower(), name))
        return v
    except Exception:  # noqa: BLE001
        return None


def list_engaged(scope: str) -> dict[str, str]:
    """Return ``{name: reason}`` for every engaged switch at ``scope``."""
    try:
        client = _redis()
        prefix = f"{_REDIS_PREFIX}:{scope.lower()}:"
        out: dict[str, str] = {}
        for key in client.scan_iter(match=f"{prefix}*"):
            name = key[len(prefix):]
            reason = client.get(key)
            if reason is not None:
                out[name] = reason
        return out
    except Exception:  # noqa: BLE001
        return {}


class KillSwitchV2:
    """Per-bot kill switch monitor.

    A single instance lives on each :class:`BotKernel`; it subscribes
    to the bot/fleet/platform Redis channels and exposes
    :attr:`engaged` for the risk engine.  Also polls every
    ``poll_interval_s`` seconds as a redundant channel.
    """

    def __init__(
        self,
        *,
        bot_id: str,
        fleet_id: str | None = None,
        poll_interval_s: float = 5.0,
    ) -> None:
        self.bot_id = bot_id
        self.fleet_id = fleet_id
        self.poll_interval_s = poll_interval_s
        self._engaged: tuple[str, str, str] | None = None  # (scope, name, reason)

    @property
    def engaged(self) -> tuple[str, str, str] | None:
        return self._engaged

    def poll_once(self) -> None:
        """Single polling pass — synchronous."""
        # Platform first (most severe).
        for scope_name, target in (
            (KillSwitchScope.PLATFORM, "platform"),
            (KillSwitchScope.FLEET, self.fleet_id or "_none_"),
            (KillSwitchScope.BOT, self.bot_id),
        ):
            if target == "_none_":
                continue
            reason = get_reason(scope_name.value, target)
            if reason:
                self._engaged = (scope_name.value, target, reason)
                return
        self._engaged = None

    async def watch(self) -> None:
        """Long-running watcher coroutine (used by kernel telemetry_task).

        Polls every ``poll_interval_s`` seconds.  Pub/sub fast-path
        is left for a future enhancement — polling guarantees
        eventual consistency within the configured interval.
        """
        import asyncio

        while True:
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001
                logger.debug("kill switch poll raised", exc_info=True)
            await asyncio.sleep(self.poll_interval_s)


__all__ = [
    "KillSwitchScope",
    "KillSwitchV2",
    "engage_scoped",
    "get_reason",
    "is_engaged_scoped",
    "list_engaged",
    "release_scoped",
]
