"""dbt build sink for data-engine manifests."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from aqp.data.dbt.project import DbtProjectManager
from aqp.data.dbt.runner import DbtRunnerService
from aqp.data.engine.nodes import NodeContext, SinkNode
from aqp.data.engine.registry import register_node

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "sink.dbt_build",
    description="Run a scoped dbt build against the local DuckDB project.",
    tags=("dbt", "duckdb", "transform"),
)
class DbtBuildSink(SinkNode):
    """Drain the upstream stream and trigger ``dbt build --select ...``."""

    def __init__(
        self,
        *,
        select: list[str] | str | None = None,
        drain_input: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if isinstance(select, str):
            self.select = [select]
        else:
            self.select = list(select or [])
        self.drain_input = bool(drain_input)

    def write(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> dict[str, Any]:
        rows_seen = 0
        if self.drain_input:
            for batch in batches:
                rows_seen += int(getattr(batch, "num_rows", 0) or 0)

        selectors = self.select or ["tag:aqp_generated"]
        ctx.emit("dbt", f"running dbt build select={','.join(selectors)}")
        runner = DbtRunnerService(DbtProjectManager.from_settings())
        result = runner.build(select=selectors)
        if result.success:
            ctx.emit("dbt", "dbt build finished")
        else:
            ctx.emit("dbt_error", result.exception or "dbt build failed")

        return {
            "rows_written": rows_seen,
            "family": "dbt",
            "identifier": ",".join(selectors),
            "name": "dbt_build",
            "error": result.exception if not result.success else None,
            "lineage": {"dbt_select": selectors},
            "extras": [
                {
                    "kind": "dbt_build",
                    "success": result.success,
                    "artifacts": result.artifacts,
                    "models_count": len(result.models),
                }
            ],
        }
