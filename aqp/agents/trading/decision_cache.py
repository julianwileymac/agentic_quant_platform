"""Parquet + DuckDB cache for :class:`AgentDecision` objects.

Used by the agentic backtest flow so that a backtest can read
pre-computed decisions without re-running the LLM crew, and so that
re-running a backtest with the same (strategy, symbol, timestamp,
context) is deterministic.

On-disk layout::

    {settings.agentic_cache_dir}/
      decisions/strategy_id={sid}/symbol={sym}/dt={yyyy-mm-dd}/*.parquet
      index.duckdb              # optional; DuckDB view built on demand

Each Parquet row carries the **full serialized decision payload** so
the Decision Timeline UI can render analyst reports + debate without
joining another table. A DB row (:class:`aqp.persistence.models.AgentDecision`)
is written alongside when the caller supplies a ``db_writer`` callback;
that is the Celery task's job.

Key design decisions:

- **Context hash as primary key.** ``context_hash`` is computed by the
  trader crew at ``run_trader_crew`` time. Two calls for the same
  symbol + date but different model/news snapshots will cache as
  distinct rows; most of the time the older row still wins because
  dates don't repeat.
- **Per-day files.** Small files over sub-directories give fast
  ``(symbol, date)`` lookups without loading the whole cache.
- **Idempotent writes.** ``put`` skips writes when the file exists
  unless ``overwrite`` is set, so re-runs of the Celery task don't
  explode disk usage.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.agents.trading.types import AgentDecision
from aqp.config import settings

logger = logging.getLogger(__name__)


def _day_str(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d")


def _safe_symbol(sym: str) -> str:
    """Sanitize a vt_symbol for use as a directory name."""
    return sym.replace("/", "_").replace("\\", "_")


class DecisionCache:
    """Parquet-backed decision store.

    Parameters
    ----------
    root:
        Root directory. Defaults to :data:`settings.agentic_cache_dir`.
    strategy_id:
        Optional logical grouping. Lets the same cache directory hold
        decisions for many strategies without collisions.
    """

    def __init__(
        self,
        root: Path | str | None = None,
        strategy_id: str | None = None,
    ) -> None:
        base = Path(root) if root else Path(settings.agentic_cache_dir)
        self.strategy_id = strategy_id or "default"
        self.root = base / "decisions" / f"strategy_id={self.strategy_id}"
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # File layout helpers
    # ------------------------------------------------------------------

    def _partition(self, vt_symbol: str, ts: datetime) -> Path:
        return (
            self.root
            / f"symbol={_safe_symbol(vt_symbol)}"
            / f"dt={_day_str(ts)}"
        )

    def _filename(self, vt_symbol: str, ts: datetime, context_hash: str) -> Path:
        h = context_hash or "default"
        return self._partition(vt_symbol, ts) / f"{h[:16]}.parquet"

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def put(self, decision: AgentDecision, *, overwrite: bool = False) -> Path:
        """Write a decision Parquet file and return the path."""
        part = self._partition(decision.vt_symbol, decision.timestamp)
        part.mkdir(parents=True, exist_ok=True)
        path = self._filename(
            decision.vt_symbol, decision.timestamp, decision.context_hash
        )
        if path.exists() and not overwrite:
            return path
        payload = decision.to_json_dict()
        row = {
            "vt_symbol": decision.vt_symbol,
            "timestamp": decision.timestamp.isoformat(),
            "action": decision.action.value if hasattr(decision.action, "value") else str(decision.action),
            "size_pct": float(decision.size_pct),
            "confidence": float(decision.confidence),
            "rating": decision.rating.value if hasattr(decision.rating, "value") else str(decision.rating),
            "rationale": decision.rationale,
            "provider": decision.provider,
            "deep_model": decision.deep_model,
            "quick_model": decision.quick_model,
            "token_cost_usd": float(decision.token_cost_usd),
            "context_hash": decision.context_hash,
            "crew_run_id": decision.crew_run_id or "",
            "payload_json": json.dumps(payload, default=str),
        }
        pd.DataFrame([row]).to_parquet(path, index=False)
        return path

    def get(self, vt_symbol: str, ts: datetime) -> AgentDecision | None:
        """Return the most recently written decision for ``(symbol, ts)``.

        Falls back to ``None`` on cache miss. Ignores ``context_hash`` so
        callers can hit the cache without recomputing every tool snapshot
        first — if you need strict context matching, pass the hash via
        :meth:`get_by_hash` or use the ``force`` flag on
        :func:`aqp.agents.trading.propagate.propagate`.
        """
        part = self._partition(vt_symbol, ts)
        if not part.exists():
            return None
        files = sorted(
            part.glob("*.parquet"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            return None
        df = pd.read_parquet(files[0])
        if df.empty:
            return None
        return self._row_to_decision(df.iloc[0])

    def get_by_hash(self, vt_symbol: str, ts: datetime, context_hash: str) -> AgentDecision | None:
        """Strict lookup keyed on ``context_hash``."""
        path = self._filename(vt_symbol, ts, context_hash)
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty:
            return None
        return self._row_to_decision(df.iloc[0])

    def scan(
        self,
        vt_symbols: Iterable[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Return a tidy DataFrame of every cached decision matching the filters.

        Used by :class:`AgenticAlpha` to preload decisions into memory at
        backtest start, and by the REST surface for the Decision Timeline.
        """
        rows: list[dict[str, Any]] = []
        symbols = (
            {_safe_symbol(s) for s in vt_symbols} if vt_symbols else None
        )
        for sym_dir in sorted(self.root.glob("symbol=*/")):
            sym = sym_dir.name.split("=", 1)[1]
            if symbols is not None and sym not in symbols:
                continue
            for dt_dir in sorted(sym_dir.glob("dt=*/")):
                day = dt_dir.name.split("=", 1)[1]
                try:
                    day_dt = datetime.strptime(day, "%Y-%m-%d")
                except ValueError:
                    continue
                if start and day_dt < start:
                    continue
                if end and day_dt > end:
                    continue
                for path in dt_dir.glob("*.parquet"):
                    try:
                        df = pd.read_parquet(path)
                        rows.extend(df.to_dict(orient="records"))
                    except Exception as exc:  # pragma: no cover
                        logger.warning("failed to read %s: %s", path, exc)
        if not rows:
            return pd.DataFrame(columns=[
                "vt_symbol", "timestamp", "action", "size_pct", "confidence",
                "rating", "rationale", "token_cost_usd", "context_hash",
            ])
        df = pd.DataFrame(rows)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.sort_values(["vt_symbol", "timestamp"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Bulk helpers
    # ------------------------------------------------------------------

    def bulk_precompute(
        self,
        symbols: Iterable[str],
        dates: Iterable[datetime],
        *,
        config: Any | None = None,
        on_progress: Any | None = None,
        force: bool = False,
    ) -> list[AgentDecision]:
        """Precompute decisions for every ``(symbol, date)`` pair.

        Uses :func:`aqp.agents.trading.propagate.propagate` under the hood.
        Calls ``on_progress(pct, message)`` (if provided) after each
        decision so Celery tasks can stream updates.
        """
        from aqp.agents.trading.propagate import propagate

        dates_list = list(dates)
        syms_list = list(symbols)
        total = max(1, len(dates_list) * len(syms_list))
        out: list[AgentDecision] = []
        done = 0
        for dt in dates_list:
            for sym in syms_list:
                try:
                    decision = propagate(
                        sym,
                        dt,
                        config=config,
                        cache=self,
                        force=force,
                    )
                    out.append(decision)
                except Exception as exc:  # pragma: no cover - runtime network
                    logger.warning("propagate failed for %s @ %s: %s", sym, dt, exc)
                done += 1
                if on_progress is not None:
                    try:
                        on_progress(done / total, f"{sym} @ {dt.date() if hasattr(dt, 'date') else dt}")
                    except Exception:  # pragma: no cover
                        pass
        return out

    def total_cost_usd(self) -> float:
        """Sum the ``token_cost_usd`` across every cached decision."""
        df = self.scan()
        if df.empty:
            return 0.0
        return float(df["token_cost_usd"].sum())

    # ------------------------------------------------------------------
    # Row <-> decision conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_decision(row: pd.Series) -> AgentDecision:
        payload = row.get("payload_json", "")
        if isinstance(payload, str) and payload:
            try:
                return AgentDecision.model_validate(json.loads(payload))
            except Exception:
                pass
        # Minimal fallback using only the top-level columns.
        from aqp.agents.trading.types import Rating5, TraderAction

        return AgentDecision(
            vt_symbol=str(row["vt_symbol"]),
            timestamp=pd.to_datetime(row["timestamp"]).to_pydatetime(),
            action=TraderAction(row.get("action", "HOLD")),
            size_pct=float(row.get("size_pct", 0.0) or 0.0),
            confidence=float(row.get("confidence", 0.5) or 0.5),
            rating=Rating5(row.get("rating", "hold")),
            rationale=str(row.get("rationale", "") or ""),
            token_cost_usd=float(row.get("token_cost_usd", 0.0) or 0.0),
            context_hash=str(row.get("context_hash", "") or ""),
            crew_run_id=str(row.get("crew_run_id", "") or "") or None,
        )


def get_default_cache(strategy_id: str | None = None) -> DecisionCache:
    """Convenience factory for the default cache location."""
    return DecisionCache(strategy_id=strategy_id)
