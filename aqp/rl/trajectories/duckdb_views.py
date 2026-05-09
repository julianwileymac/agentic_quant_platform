"""DuckDB views over the four ``rl.*`` Iceberg tables.

Powers the API ``/rl/runs/{id}/equity`` /
``/rl/runs/{id}/trajectories`` /
``/rl/runs/{id}/reward-decomposition`` endpoints without making the UI
request go through PyIceberg.

Views are created on demand on a connection-local namespace
(``rl_trajectories``, ``rl_equity_curves``, …) and re-pointed at the
current Iceberg snapshot via the existing
:mod:`aqp.data.duckdb_engine` shim.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _iceberg_namespace_table() -> tuple[str, dict[str, str]]:
    from aqp.config import settings

    namespace = getattr(settings, "rl_trajectory_namespace", "rl")
    return namespace, {
        "trajectories": getattr(settings, "rl_trajectory_table", "trajectories"),
        "equity_curves": getattr(settings, "rl_equity_table", "equity_curves"),
        "action_logs": getattr(settings, "rl_action_log_table", "action_logs"),
        "reward_decomposition": getattr(
            settings, "rl_reward_decomp_table", "reward_decomposition"
        ),
    }


def ensure_duckdb_views(connection: Any | None = None) -> dict[str, str]:
    """Create / refresh DuckDB views over the four RL Iceberg tables.

    Returns a mapping ``{logical_name: view_name}`` for the caller to
    use in ``SELECT`` statements. When DuckDB / pyiceberg / the catalog
    is unavailable the function returns an empty dict and logs at debug
    level so callers can fall back to in-memory data.
    """
    namespace, tables = _iceberg_namespace_table()
    out: dict[str, str] = {}
    try:
        from aqp.data import iceberg_catalog
    except Exception:  # pragma: no cover
        return out
    if connection is None:
        try:
            import duckdb

            connection = duckdb.connect(":memory:")
        except Exception:  # pragma: no cover
            return out

    for kind, table_name in tables.items():
        view = f"rl_{kind}"
        try:
            arrow_table = iceberg_catalog.read_arrow(f"{namespace}.{table_name}")
        except Exception:  # noqa: BLE001
            logger.debug(
                "ensure_duckdb_views: could not read %s.%s",
                namespace,
                table_name,
                exc_info=True,
            )
            continue
        if arrow_table is None:
            continue
        try:
            connection.register(f"_arrow_{view}", arrow_table)
            connection.execute(
                f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM _arrow_{view}"
            )
            out[kind] = view
        except Exception:  # noqa: BLE001
            logger.debug("DuckDB view registration failed for %s", view, exc_info=True)
    return out


def register_run_views(run_id: str, connection: Any | None = None) -> dict[str, str]:
    """Register DuckDB views filtered to a single ``run_id``.

    Returns ``{kind: view_name}``. The filtered views are named
    ``rl_<kind>_run_<short_id>`` to avoid clashing across runs.
    """
    out: dict[str, str] = {}
    base = ensure_duckdb_views(connection=connection)
    if not base or connection is None:
        return out
    short = run_id.replace("-", "")[:12]
    for kind, view in base.items():
        filt = f"rl_{kind}_run_{short}"
        try:
            connection.execute(
                f"CREATE OR REPLACE VIEW {filt} AS "
                f"SELECT * FROM {view} WHERE run_id = $run_id",
                {"run_id": run_id},
            )
            out[kind] = filt
        except Exception:  # noqa: BLE001
            logger.debug("filtered view creation failed for %s", filt, exc_info=True)
    return out


__all__ = ["ensure_duckdb_views", "register_run_views"]
