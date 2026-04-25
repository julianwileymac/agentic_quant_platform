"""Corporate-actions metadata — Lean's ``MapFile`` / ``FactorFile`` pattern.

Two CSV-backed types sit alongside the Parquet price lake:

- **`MapFile`** tracks a ticker's lineage across renames / mergers. Each
  row is a ``(date, ticker)`` pair; the most recent entry at a given
  date is the ticker effective on/before that date.
- **`FactorFile`** carries per-date split and dividend factors. When the
  caller requests ``DataNormalizationMode.ADJUSTED`` or
  ``SPLIT_ADJUSTED``, we multiply prices by the rolling factor so the
  data feed surface stays timezone/split-agnostic.

Files live under ``<data_root>/auxiliary/{map_files,factor_files}/``:

- ``map_files/<ticker>.csv`` — ``date,ticker``
- ``factor_files/<ticker>.csv`` — ``date,price_factor,split_factor``
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from aqp.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MapFile
# ---------------------------------------------------------------------------


@dataclass
class MapFileEntry:
    date: date
    ticker: str


@dataclass
class MapFile:
    """Per-symbol ticker history (oldest first)."""

    vt_symbol: str
    entries: list[MapFileEntry] = field(default_factory=list)

    def ticker_at(self, ts: datetime | date) -> str:
        """Ticker effective on/before ``ts``. Falls back to the first entry."""
        target = ts.date() if isinstance(ts, datetime) else ts
        effective = self.entries[0].ticker if self.entries else self.vt_symbol
        for entry in self.entries:
            if entry.date <= target:
                effective = entry.ticker
            else:
                break
        return effective

    @classmethod
    def load(cls, path: str | Path) -> MapFile:
        path = Path(path)
        entries: list[MapFileEntry] = []
        with path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if not row or row[0].startswith("#"):
                    continue
                d = date.fromisoformat(row[0].strip())
                ticker = row[1].strip().upper()
                entries.append(MapFileEntry(d, ticker))
        entries.sort(key=lambda e: e.date)
        vt = entries[-1].ticker if entries else path.stem.upper()
        return cls(vt_symbol=vt, entries=entries)


# ---------------------------------------------------------------------------
# FactorFile
# ---------------------------------------------------------------------------


@dataclass
class FactorFileEntry:
    date: date
    price_factor: float
    split_factor: float


@dataclass
class FactorFile:
    """Per-symbol split/dividend adjustment factors (oldest first)."""

    vt_symbol: str
    entries: list[FactorFileEntry] = field(default_factory=list)

    def factor_at(self, ts: datetime | date) -> tuple[float, float]:
        """Return ``(price_factor, split_factor)`` effective at ``ts``."""
        target = ts.date() if isinstance(ts, datetime) else ts
        pf, sf = 1.0, 1.0
        for entry in self.entries:
            if entry.date <= target:
                pf, sf = entry.price_factor, entry.split_factor
            else:
                break
        return pf, sf

    def adjust_price(self, price: float, ts: datetime | date) -> float:
        pf, sf = self.factor_at(ts)
        return price * pf * sf

    def adjust_bars(
        self,
        bars: pd.DataFrame,
        mode: str = "adjusted",
    ) -> pd.DataFrame:
        """Apply factors to every row of a tidy bars frame.

        ``mode``:
        - ``"adjusted"`` — multiply OHLC by ``price_factor * split_factor``;
          divide volume by ``split_factor``.
        - ``"split_adjusted"`` — only split factor.
        - ``"raw"`` — no-op.
        """
        if mode == "raw" or bars.empty or not self.entries:
            return bars
        df = bars.copy()
        # merge_asof requires numeric / datetime keys on both sides, so coerce
        # our ``date`` objects into ``Timestamp``.
        df["_factor_ts"] = pd.to_datetime(df["timestamp"]).dt.normalize()
        factor_df = pd.DataFrame(
            [
                (pd.Timestamp(e.date), e.price_factor, e.split_factor)
                for e in self.entries
            ],
            columns=["factor_date", "price_factor", "split_factor"],
        ).sort_values("factor_date")
        df = pd.merge_asof(
            df.sort_values("_factor_ts"),
            factor_df.rename(columns={"factor_date": "_factor_ts"}),
            on="_factor_ts",
            direction="backward",
        )
        df["price_factor"] = df["price_factor"].fillna(1.0)
        df["split_factor"] = df["split_factor"].fillna(1.0)
        if mode == "adjusted":
            adjust = df["price_factor"] * df["split_factor"]
        elif mode == "split_adjusted":
            adjust = df["split_factor"]
        else:
            raise ValueError(f"unknown normalization mode: {mode!r}")
        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                df[col] = df[col] * adjust
        if "volume" in df.columns:
            df["volume"] = df["volume"] / df["split_factor"].replace(0, 1.0)
        return df.drop(columns=["_factor_ts", "price_factor", "split_factor"])

    @classmethod
    def load(cls, path: str | Path) -> FactorFile:
        path = Path(path)
        entries: list[FactorFileEntry] = []
        with path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if not row or row[0].startswith("#"):
                    continue
                d = date.fromisoformat(row[0].strip())
                price = float(row[1])
                split = float(row[2]) if len(row) > 2 else 1.0
                entries.append(FactorFileEntry(d, price, split))
        entries.sort(key=lambda e: e.date)
        vt = path.stem.upper()
        return cls(vt_symbol=vt, entries=entries)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class AuxiliaryStore:
    """Loads MapFile / FactorFile CSVs from the data lake's ``auxiliary/`` dir."""

    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root else settings.data_dir / "auxiliary"
        self.root = Path(base)
        self._map_cache: dict[str, MapFile] = {}
        self._factor_cache: dict[str, FactorFile] = {}

    def map_file(self, vt_symbol: str) -> MapFile | None:
        if vt_symbol in self._map_cache:
            return self._map_cache[vt_symbol]
        path = self.root / "map_files" / f"{_safe_name(vt_symbol)}.csv"
        if not path.exists():
            return None
        try:
            mf = MapFile.load(path)
        except Exception:
            logger.exception("failed to load map file %s", path)
            return None
        self._map_cache[vt_symbol] = mf
        return mf

    def factor_file(self, vt_symbol: str) -> FactorFile | None:
        if vt_symbol in self._factor_cache:
            return self._factor_cache[vt_symbol]
        path = self.root / "factor_files" / f"{_safe_name(vt_symbol)}.csv"
        if not path.exists():
            return None
        try:
            ff = FactorFile.load(path)
        except Exception:
            logger.exception("failed to load factor file %s", path)
            return None
        self._factor_cache[vt_symbol] = ff
        return ff

    def apply_adjustments(
        self,
        bars: pd.DataFrame,
        vt_symbol: str,
        mode: str = "adjusted",
    ) -> pd.DataFrame:
        if mode == "raw":
            return bars
        ff = self.factor_file(vt_symbol)
        if ff is None:
            return bars
        return ff.adjust_bars(bars, mode=mode)


def _safe_name(vt_symbol: str) -> str:
    return vt_symbol.replace(".", "_").replace("/", "_")
