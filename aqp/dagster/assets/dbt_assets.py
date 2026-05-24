"""dagster-dbt @dbt_assets wrapper on top of DbtRunnerService (Phase 2).

Closes the exploration gap: AQP already ships a Python
``DbtRunnerService`` + ``DbtProjectManager`` but has no
``@dbt_assets``-style wrapper, so dbt models do not appear as
Dagster SDAs today. This module builds the wrapper. When
``dagster-dbt`` is installed, importing this file generates one
Dagster asset per dbt model in the AQP mesh; when it isn't, the
import is a no-op so the rest of the Dagster code locations keep
loading.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def build_dbt_assets_for_project(
    *,
    project_slug: str = "core",
    manifest_relative: str = "target/manifest.json",
    select: str | None = None,
) -> list[Any]:
    """Generate Dagster assets for one dbt project in the AQP mesh."""
    project_dir = Path(__file__).resolve().parents[3] / "data" / "dbt" / "projects" / project_slug
    manifest_path = project_dir / manifest_relative
    try:
        from dagster_dbt import (  # type: ignore[import-not-found]
            DbtCliResource,
            dbt_assets,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "dagster-dbt not installed (%s); skipping dbt SDA generation", exc
        )
        return []
    if not manifest_path.exists():
        logger.info(
            "dbt manifest not yet compiled at %s; run `dbt parse` first",
            manifest_path,
        )
        return []

    @dbt_assets(manifest=manifest_path, select=select)
    def _generated(context, dbt: DbtCliResource):  # type: ignore[no-redef]
        yield from dbt.cli(["build"], context=context).stream()

    return [_generated]


def build_all_mesh_assets() -> list[Any]:
    """Generate Dagster assets for every team project under ``projects/``."""
    base = Path(__file__).resolve().parents[3] / "data" / "dbt" / "projects"
    if not base.exists():
        return []
    out: list[Any] = []
    for project_dir in sorted(base.iterdir()):
        if not project_dir.is_dir():
            continue
        out.extend(build_dbt_assets_for_project(project_slug=project_dir.name))
    return out


__all__ = ["build_all_mesh_assets", "build_dbt_assets_for_project"]
