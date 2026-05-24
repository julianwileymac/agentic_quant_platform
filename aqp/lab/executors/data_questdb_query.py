"""``data.questdb_query`` — PGWire query against QuestDB via asyncpg."""
from __future__ import annotations

import logging

import pandas as pd

from aqp.lab.executors._helpers import base_locator, stash_arrow_output
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    sql = str(params.get("sql") or "").strip()
    if not sql:
        return NodeResult(status="error", error="data.questdb_query needs non-empty 'sql'")

    try:
        from aqp.data.timeseries.questdb_client import QuestDBClient
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"questdb_client unavailable: {exc}")

    try:
        client = QuestDBClient()
        records = client.fetch(sql) if hasattr(client, "fetch") else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("QuestDB query failed: %s", exc)
        return NodeResult(status="error", error=f"QuestDB query failed: {exc}")

    df = pd.DataFrame(list(records or []))
    stash_arrow_output(ctx, node.id, df)
    return NodeResult(
        status="done",
        output_locator={**base_locator(node.id, df), "sql_first_64": sql[:64]},
        metrics={"rows": int(len(df))},
        log_label=f"questdb:{len(df)} rows",
    )
