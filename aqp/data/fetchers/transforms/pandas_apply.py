"""Apply an arbitrary pandas function to every batch.

Convenient escape hatch for the Manifest Builder when neither
``arrow_select`` / ``arrow_filter`` / ``arrow_join`` cover the
desired transformation. Accepts a dotted callable reference so
manifests stay JSON-serializable.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, TransformNode
from aqp.data.engine.registry import register_node

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "transform.pandas_apply",
    description="Apply a Python callable to each batch as pandas DataFrame.",
    tags=("pandas",),
)
class PandasApplyTransform(TransformNode):
    """Apply ``callable_path`` (``module.func``) to every batch.

    The callable receives a pandas DataFrame and must return one. ``kwargs``
    are forwarded as keyword arguments.
    """

    def __init__(
        self,
        *,
        callable_path: str,
        kwargs: dict[str, Any] | None = None,
        **node_kwargs: Any,
    ) -> None:
        super().__init__(**node_kwargs)
        self.callable_path = callable_path
        self.callable_kwargs = dict(kwargs or {})
        self._fn: Callable[..., Any] | None = None

    def _resolve(self) -> Callable[..., Any]:
        if self._fn is not None:
            return self._fn
        module_path, fn_name = self.callable_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        fn = getattr(mod, fn_name, None)
        if not callable(fn):
            raise TypeError(f"pandas_apply: {self.callable_path!r} is not callable")
        self._fn = fn
        return fn

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa

        fn = self._resolve()
        for batch in batches:
            df = batch.to_pandas()
            new_df = fn(df, **self.callable_kwargs)
            if new_df is None or len(new_df) == 0:
                continue
            table = pa.Table.from_pandas(new_df, preserve_index=False)
            yield from table.to_batches()
