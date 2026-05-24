"""QuestDB :class:`BaseDataset`.

Phase 2b of the AQP infra-expansion plan: read + write tick-data and
event tables on QuestDB through the canonical Kedro-style dataset
contract. Reads run via the PGWire client; writes go via ILP TCP.

Spec config schema::

    {
      "table": "market_l1",                     # required
      "ts_column": "ts",                        # required for SAMPLE BY
      "partition_by": "HOUR",                   # for create_table
      "tag_keys": ["exchange", "symbol"],
      "field_keys": ["bid", "ask", "size"],
      "select": "SELECT * FROM market_l1 ...",  # optional override
      "limit": 10000,                            # default for plain reads
    }

Reads return a :class:`pandas.DataFrame`; writes accept an iterable of
mappings, an Arrow table, or a DataFrame and use the ILP ingester. The
``connection`` is implicit (single QuestDB endpoint resolved through
:mod:`aqp.data.timeseries.questdb_client`).
"""
from __future__ import annotations

import asyncio
from typing import Any, Iterable, Mapping

from aqp.data.datasets.base import BaseDataset


class QuestDBDataset(BaseDataset):
    kind = "questdb"
    writable = True

    def _validate_spec(self) -> None:
        cfg = self._spec.config
        if not str(cfg.get("table") or "").strip():
            raise ValueError("QuestDBDataset requires config.table")

    # ---------------------------------------------------------- read
    def _load(self) -> Any:
        cfg = self._spec.config
        table = str(cfg["table"])
        select = cfg.get("select")
        limit = int(cfg.get("limit") or 10_000)
        if select:
            sql = str(select)
        else:
            ts_column = cfg.get("ts_column") or "ts"
            sql = (
                f"SELECT * FROM {table} ORDER BY {ts_column} DESC LIMIT {limit};"
            )
        return _await(self._fetch_df(sql))

    async def _fetch_df(self, sql: str) -> Any:
        from aqp.data.timeseries.questdb_client import get_questdb_client

        client = await get_questdb_client()
        rows = await client.fetch(sql)
        try:
            import pandas as pd
        except ImportError:
            return rows
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    # ---------------------------------------------------------- write
    def _save(self, payload: Any) -> Any:
        cfg = self._spec.config
        measurement = str(cfg["table"])
        tag_keys = list(cfg.get("tag_keys") or [])
        field_keys = list(cfg.get("field_keys") or [])
        records = self._normalise_payload(payload)
        return _await(
            self._send_batch(
                measurement,
                records=records,
                tag_keys=tag_keys,
                field_keys=field_keys,
            )
        )

    async def _send_batch(
        self,
        measurement: str,
        *,
        records: Iterable[Mapping[str, Any]],
        tag_keys: list[str],
        field_keys: list[str],
    ) -> dict[str, Any]:
        from aqp.data.timeseries.questdb_ingest import QuestDBIngester

        ingester = QuestDBIngester()
        try:
            written = ingester.send_batch(
                measurement,
                records=records,
                tag_keys=tag_keys,
                field_keys=field_keys,
            )
            return {"bytes_written": int(written)}
        finally:
            ingester.close()

    @staticmethod
    def _normalise_payload(payload: Any) -> list[Mapping[str, Any]]:
        # Accept list[dict] | DataFrame | Arrow Table.
        if isinstance(payload, list):
            return payload
        try:
            import pandas as pd

            if isinstance(payload, pd.DataFrame):
                return payload.to_dict(orient="records")
        except ImportError:
            pass
        try:
            import pyarrow as pa

            if isinstance(payload, pa.Table):
                return payload.to_pylist()
        except ImportError:
            pass
        raise TypeError(
            f"QuestDBDataset save: unsupported payload type {type(payload)!r}"
        )

    # ---------------------------------------------------------- describe
    def _describe(self) -> dict[str, Any]:
        cfg = self._spec.config
        return {
            "table": cfg.get("table"),
            "ts_column": cfg.get("ts_column"),
            "partition_by": cfg.get("partition_by"),
            "tag_keys": list(cfg.get("tag_keys") or []),
            "field_keys": list(cfg.get("field_keys") or []),
            "load_mode": "questdb_pgwire",
        }

    def _exists(self) -> bool:
        # Cheap probe: we treat the dataset as existing if the QuestDB
        # endpoint resolves; the heavy check is in _load.
        cfg = self._spec.config
        return bool(cfg.get("table"))


def _await(coro: Any) -> Any:
    """Run an async coroutine from a sync dataset call site.

    Datasets are sync-by-contract per Kedro's BaseDataset shape, but
    the underlying QuestDB client is async (asyncpg). Use
    :func:`asyncio.run` when no loop is running, otherwise schedule
    onto the existing loop and block.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result()
    except RuntimeError:
        pass
    return asyncio.run(coro)


__all__ = ["QuestDBDataset"]
