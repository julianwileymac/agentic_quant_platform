"""``IcebergTrajectoryStore`` — Iceberg-backed RL trajectory persistence.

Every per-step record (env state, action, reward), per-step equity-curve
point, per-asset action log, and reward-decomposition slice gets buffered
in an in-memory list and flushed in Arrow batches via
:func:`aqp.data.iceberg_catalog.append_arrow`.

Tables (all in the ``rl`` namespace by default — overridable via
:data:`aqp.config.settings`):

- ``rl.trajectories`` — per-step env record
  ``(run_id, episode, step, ts, reward, info_json)``
- ``rl.equity_curves`` — per-step equity / drawdown / cash
- ``rl.action_logs`` — per-asset action values per step
- ``rl.reward_decomposition`` — per-term reward contribution

The DuckDB-view registration in :mod:`aqp.rl.trajectories.duckdb_views`
makes these queryable without touching PyIceberg directly.
"""
from __future__ import annotations

import json
import logging
from typing import Any, ClassVar, Iterable, Mapping

from aqp.rl.core.replay import BaseTrajectoryStore

logger = logging.getLogger(__name__)


def table_identifier(table_kind: str) -> tuple[str, str]:
    """Return ``(namespace, table)`` for one of the four RL tables.

    ``table_kind`` ∈ ``{"trajectories", "equity_curves", "action_logs",
    "reward_decomposition"}``.
    """
    from aqp.config import settings

    namespace = getattr(settings, "rl_trajectory_namespace", "rl")
    mapping = {
        "trajectories": getattr(settings, "rl_trajectory_table", "trajectories"),
        "equity_curves": getattr(settings, "rl_equity_table", "equity_curves"),
        "action_logs": getattr(settings, "rl_action_log_table", "action_logs"),
        "reward_decomposition": getattr(
            settings, "rl_reward_decomp_table", "reward_decomposition"
        ),
    }
    return namespace, mapping[table_kind]


class IcebergTrajectoryStore(BaseTrajectoryStore):
    """Buffered Arrow writer that flushes to four ``rl.*`` Iceberg tables.

    Parameters
    ----------
    run_id:
        UUID of the run owning the buffered records (stamped on every row).
    flush_every:
        Approximate row count threshold per table — when any of the four
        buffers crosses ``flush_every`` rows we trigger a partial flush.
    context:
        Optional :class:`aqp.auth.context.RequestContext` forwarded to
        :func:`append_arrow` for tenancy stamping.
    """

    rl_alias: ClassVar[str] = "IcebergTrajectoryStore"
    rl_source: ClassVar[str] = "aqp"
    rl_tags: ClassVar[tuple[str, ...]] = ("iceberg", "default")

    def __init__(
        self,
        *,
        run_id: str | None = None,
        flush_every: int | None = None,
        context: Any | None = None,
    ) -> None:
        from aqp.config import settings

        self.run_id = run_id
        self.flush_every = int(
            flush_every
            if flush_every is not None
            else getattr(settings, "rl_trajectory_flush_rows", 1000)
        )
        self.context = context
        self._steps: list[dict[str, Any]] = []
        self._equity: list[dict[str, Any]] = []
        self._actions: list[dict[str, Any]] = []
        self._rewards: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ buffer

    def append_step(self, record: Mapping[str, Any]) -> None:
        d = dict(record)
        info = d.get("info")
        if isinstance(info, dict):
            try:
                d["info"] = json.dumps(info, default=str)
            except Exception:  # noqa: BLE001
                d["info"] = str(info)
        self._steps.append(d)
        self._maybe_flush()

    def append_equity(self, record: Mapping[str, Any]) -> None:
        self._equity.append(dict(record))
        self._maybe_flush()

    def append_action(self, record: Mapping[str, Any]) -> None:
        self._actions.append(dict(record))
        self._maybe_flush()

    def append_reward_decomposition(self, records: Iterable[Mapping[str, Any]]) -> None:
        for r in records:
            self._rewards.append(dict(r))
        self._maybe_flush()

    # ------------------------------------------------------------------ flush

    def _maybe_flush(self) -> None:
        if max(len(self._steps), len(self._equity), len(self._actions), len(self._rewards)) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        try:
            self._flush_table("trajectories", self._steps)
            self._flush_table("equity_curves", self._equity)
            self._flush_table("action_logs", self._actions)
            self._flush_table("reward_decomposition", self._rewards)
        except Exception:  # noqa: BLE001
            logger.exception("trajectory store flush failed")

    def _flush_table(self, kind: str, buffer: list[dict[str, Any]]) -> None:
        if not buffer:
            return
        try:
            import pyarrow as pa
        except Exception:  # pragma: no cover
            logger.warning("pyarrow unavailable — dropping RL %s buffer (%d rows)", kind, len(buffer))
            buffer.clear()
            return
        try:
            from aqp.data.iceberg_catalog import append_arrow
        except Exception:  # pragma: no cover
            logger.warning("iceberg_catalog unavailable — keeping RL %s buffer in memory", kind)
            return
        namespace, table = table_identifier(kind)
        identifier = f"{namespace}.{table}"
        try:
            arrow_table = pa.Table.from_pylist(buffer)
        except Exception:  # noqa: BLE001
            logger.exception("could not coerce RL %s buffer to Arrow", kind)
            buffer.clear()
            return
        try:
            append_arrow(identifier, arrow_table, context=self.context)
            buffer.clear()
        except Exception:  # noqa: BLE001
            from aqp.config import settings

            if getattr(settings, "rl_require_iceberg", False):
                raise
            logger.exception("append_arrow failed for %s — dropping buffer", identifier)
            buffer.clear()


__all__ = ["IcebergTrajectoryStore", "table_identifier"]
