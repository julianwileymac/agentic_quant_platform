"""Ray Data compute backend (lazy import)."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from aqp.data.compute.backend import ComputeBackend, ComputeBackendUnavailableError

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


def _require_ray() -> Any:
    try:
        import ray
        from ray import data as ray_data  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - optional dep import
        raise ComputeBackendUnavailableError(
            f"Ray backend unavailable: {exc}. Install with `pip install 'ray[data]'`."
        ) from exc
    return ray


class RayBackend(ComputeBackend):
    """Ray Data backend.

    The backend lazily initializes Ray on first use using ``address``
    (and any extra init kwargs supplied via the manifest's
    ``compute.extras``). It does not shut Ray down on close so other
    AQP components (e.g. Ray Serve) keep running.
    """

    name = "ray"

    def __init__(
        self,
        *,
        address: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.address = address
        self.extras = self._coerce_extras(extras)
        self._ray: Any | None = None
        self._owns_ray: bool = False

    @staticmethod
    def _coerce_extras(extras: Any) -> dict[str, Any]:
        if extras is None:
            return {}
        if isinstance(extras, str):
            try:
                return dict(json.loads(extras))
            except Exception:  # noqa: BLE001
                return {}
        if isinstance(extras, dict):
            return dict(extras)
        return {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> None:
        if self._ray is not None:
            return
        ray = _require_ray()
        if not ray.is_initialized():
            init_kwargs = dict(self.extras)
            if self.address:
                init_kwargs.setdefault("address", self.address)
            try:
                ray.init(**init_kwargs)
                self._owns_ray = True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "RayBackend init failed (%s); falling back to local mode",
                    exc,
                )
                ray.init(ignore_reinit_error=True)
                self._owns_ray = True
        self._ray = ray

    def shutdown(self) -> None:
        # Be conservative: never shut down Ray since other components
        # (Ray Serve) might be sharing the runtime.
        self._ray = None

    # ------------------------------------------------------------------
    # Conversions
    # ------------------------------------------------------------------

    def from_arrow(self, batches: Iterable[pa.RecordBatch]) -> Any:
        if self._ray is None:
            self.startup()
        import pyarrow as pa
        from ray import data as ray_data

        materialized = list(batches)
        if not materialized:
            return ray_data.from_arrow(pa.table({}))
        table = pa.Table.from_batches(materialized)
        return ray_data.from_arrow(table)

    def to_arrow(self, native: Any) -> pa.Table:
        import pyarrow as pa

        # Materialise via the Ray Data API; falls back to pandas if the
        # to_pandas codepath is faster on tiny datasets.
        try:
            tables = native.to_arrow_refs()
            from ray import get  # type: ignore

            blocks = get(tables)
            if not blocks:
                return pa.table({})
            return pa.concat_tables(blocks)
        except Exception:  # noqa: BLE001
            df = native.to_pandas()
            return pa.Table.from_pandas(df, preserve_index=False)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def map_partitions(
        self,
        native: Any,
        fn: Callable[[Any], Any],
    ) -> Any:
        return native.map_batches(fn, batch_format="pandas")

    def repartition(self, native: Any, npartitions: int) -> Any:
        return native.repartition(int(npartitions))

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "owns_ray": self._owns_ray,
            "extras": dict(self.extras),
        }


__all__ = ["RayBackend"]
