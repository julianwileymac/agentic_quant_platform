"""Dask-Distributed compute backend (lazy import)."""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from aqp.data.compute.backend import ComputeBackend, ComputeBackendUnavailableError

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


def _require_dask() -> tuple[Any, Any]:
    """Import Dask components or raise a structured error."""
    try:
        import dask  # noqa: F401
        import dask.dataframe as dd
        from distributed import Client
    except Exception as exc:  # noqa: BLE001 - optional dep import
        raise ComputeBackendUnavailableError(
            f"Dask backend unavailable: {exc}. "
            "Install with `pip install 'dask[distributed,dataframe]'`."
        ) from exc
    return dd, Client


class DaskBackend(ComputeBackend):
    """Dask Distributed backend.

    The backend lazily connects to ``address`` (e.g. ``tcp://...``) when
    provided. Without an address it spins up a local cluster using
    :class:`distributed.Client(processes=False)` so unit tests don't
    fork.
    """

    name = "dask"

    def __init__(
        self,
        *,
        address: str | None = None,
        n_workers: int | None = None,
        threads_per_worker: int | None = None,
        extras: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.address = address
        self.n_workers = n_workers
        self.threads_per_worker = threads_per_worker
        self.extras = dict(extras or {})
        self._client: Any | None = None
        self._dd: Any | None = None
        self._owns_client: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> None:
        dd, Client = _require_dask()
        self._dd = dd
        if self._client is not None:
            return
        if self.address:
            try:
                self._client = Client(self.address)
                self._owns_client = False
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "DaskBackend: cannot connect to %s (%s); using local cluster",
                    self.address,
                    exc,
                )
                self._client = Client(
                    processes=False,
                    n_workers=self.n_workers or 1,
                    threads_per_worker=self.threads_per_worker or 2,
                    set_as_default=False,
                )
                self._owns_client = True
        else:
            self._client = Client(
                processes=False,
                n_workers=self.n_workers or 1,
                threads_per_worker=self.threads_per_worker or 2,
                set_as_default=False,
            )
            self._owns_client = True
        logger.info("DaskBackend started (%s)", self._client.dashboard_link)

    def shutdown(self) -> None:
        if self._client is None:
            return
        try:
            if self._owns_client:
                self._client.close()
        except Exception:  # noqa: BLE001
            logger.debug("DaskBackend close failed", exc_info=True)
        self._client = None
        self._owns_client = False

    # ------------------------------------------------------------------
    # Conversions
    # ------------------------------------------------------------------

    def from_arrow(self, batches: Iterable[pa.RecordBatch]) -> Any:
        if self._dd is None:
            self.startup()
        import pyarrow as pa

        materialized = list(batches)
        if not materialized:
            table = pa.table({})
        else:
            table = pa.Table.from_batches(materialized)
        df = table.to_pandas(types_mapper=None)
        # ``npartitions`` heuristic: roughly one partition per ~250k rows.
        n = max(1, len(df) // 250_000) if len(df) else 1
        return self._dd.from_pandas(df, npartitions=n)

    def to_arrow(self, native: Any) -> pa.Table:
        import pyarrow as pa

        df = native.compute()
        return pa.Table.from_pandas(df, preserve_index=False)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def map_partitions(
        self,
        native: Any,
        fn: Callable[[Any], Any],
    ) -> Any:
        return native.map_partitions(fn)

    def repartition(self, native: Any, npartitions: int) -> Any:
        return native.repartition(npartitions=int(npartitions))

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "owns_client": self._owns_client,
            "dashboard_link": getattr(self._client, "dashboard_link", None),
        }


__all__ = ["DaskBackend"]
