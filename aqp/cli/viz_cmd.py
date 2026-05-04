"""``aqp viz`` subcommand — visualization layer operations.

Examples:

.. code-block:: shell

    # Provision Superset with curated AQP datasets / charts / dashboards
    aqp viz sync

    # Round-trip a Superset bundle as a directory of YAML
    aqp viz export --out deploy/superset/bundles/aqp_market_data
    aqp viz import deploy/superset/bundles/aqp_market_data

    # Render a Bokeh chart and dump the json_item
    aqp viz render --dataset aqp_equity.sp500_daily --kind line \
        --x timestamp --y close --groupby vt_symbol --out chart.json

    # Evict cached chart entries (file + Redis tier)
    aqp viz cache-clear --older-than-hours 24

    # Push Superset metadata into DataHub (no-op when the toggle is off)
    aqp viz datahub
"""
from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True, help="Visualization layer operations (Superset + Bokeh).")


@app.command("sync")
def sync_cmd(
    wait: bool = typer.Option(False, "--wait", help="Block until the Celery task completes (best-effort)."),
) -> None:
    """Provision Superset with the current AQP asset plan."""

    from aqp.tasks.visualization_tasks import sync_superset_assets_task

    async_result = sync_superset_assets_task.delay()
    typer.echo(f"queued: task_id={async_result.id}")
    if wait:
        try:
            result = async_result.get(timeout=300)
            typer.echo(json.dumps(result, indent=2, default=str))
        except Exception as exc:  # noqa: BLE001
            typer.secho(f"task wait failed: {exc}", fg=typer.colors.YELLOW)


@app.command("export")
def export_cmd(
    out: Path = typer.Option(..., "--out", help="Directory or .zip path to write the bundle to."),
    dashboard_id: list[int] = typer.Option(
        [],
        "--dashboard-id",
        help="Restrict export to one or more dashboard ids; omit to export everything.",
    ),
) -> None:
    """Pull a CLI-compatible Superset asset bundle and persist it on disk."""

    from aqp.services.superset_client import SupersetClient
    from aqp.visualization.superset_bundle import export_bundle, write_bundle_dir

    with SupersetClient() as client:
        zip_bytes = export_bundle(client, dashboard_ids=dashboard_id or None)

    out = Path(out)
    if out.suffix == ".zip":
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(zip_bytes)
        typer.echo(f"wrote zip ({len(zip_bytes)} bytes) → {out}")
    else:
        out.mkdir(parents=True, exist_ok=True)
        write_bundle_dir(zip_bytes, out)
        typer.echo(f"wrote bundle directory ({len(zip_bytes)} bytes) → {out}")


@app.command("import")
def import_cmd(
    source: Path = typer.Argument(..., help="Bundle directory or .zip file to push back into Superset."),
    overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite", help="Replace existing assets."),
    password: list[str] = typer.Option(
        [],
        "--password",
        help="Per-database password mapping shaped 'slug=secret' (repeatable).",
    ),
) -> None:
    """Push a previously-exported bundle back into Superset."""

    from aqp.services.superset_client import SupersetClient
    from aqp.visualization.superset_bundle import (
        import_bundle,
        import_bundle_from_dir,
    )

    passwords: dict[str, str] = {}
    for entry in password or []:
        if "=" not in entry:
            typer.secho(f"--password expects 'slug=secret', got {entry!r}", fg=typer.colors.RED)
            raise typer.Exit(code=2)
        slug, _, secret = entry.partition("=")
        passwords[slug.strip()] = secret

    source = Path(source)
    with SupersetClient() as client:
        if source.is_dir():
            response = import_bundle_from_dir(
                client, source, passwords=passwords or None, overwrite=overwrite
            )
        else:
            response = import_bundle(
                client,
                source.read_bytes(),
                passwords=passwords or None,
                overwrite=overwrite,
                filename=source.name,
            )
    typer.echo(json.dumps(response, indent=2, default=str))


@app.command("render")
def render_cmd(
    dataset: str = typer.Option(..., "--dataset", help="Iceberg identifier 'namespace.table'."),
    kind: str = typer.Option("line", "--kind"),
    x: str = typer.Option("timestamp", "--x"),
    y: str = typer.Option("close", "--y"),
    groupby: str | None = typer.Option("vt_symbol", "--groupby"),
    limit: int = typer.Option(1000, "--limit"),
    title: str | None = typer.Option(None, "--title"),
    out: Path | None = typer.Option(None, "--out", help="Write the json_item to this file."),
) -> None:
    """Render a Bokeh json_item directly via the renderer (offline-safe)."""

    from aqp.visualization.bokeh_renderer import BokehChartSpec, render_bokeh_item

    spec = BokehChartSpec(
        kind=kind,  # type: ignore[arg-type]
        dataset_identifier=dataset,
        x=x,
        y=y,
        groupby=groupby,
        limit=limit,
        title=title,
    )
    item = render_bokeh_item(spec)
    payload = json.dumps(item, default=str)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(payload, encoding="utf-8")
        typer.echo(f"wrote {len(payload)} bytes → {out}")
    else:
        typer.echo(payload)


@app.command("cache-clear")
def cache_clear_cmd(
    older_than_hours: float | None = typer.Option(
        None,
        "--older-than-hours",
        help="Only evict entries older than N hours; omit to clear everything.",
    ),
) -> None:
    """Evict cached Bokeh charts from both file and Redis tiers."""

    from aqp.visualization.bokeh_renderer import clear_cache

    seconds = int(older_than_hours * 3600) if older_than_hours is not None else None
    summary = clear_cache(older_than_seconds=seconds)
    typer.echo(json.dumps(summary, indent=2))


@app.command("datahub")
def datahub_cmd(
    wait: bool = typer.Option(False, "--wait", help="Block until the push completes."),
) -> None:
    """Push Superset metadata into DataHub (no-op when toggle is off)."""

    from aqp.tasks.visualization_tasks import push_superset_to_datahub_task

    async_result = push_superset_to_datahub_task.delay()
    typer.echo(f"queued: task_id={async_result.id}")
    if wait:
        try:
            result = async_result.get(timeout=600)
            typer.echo(json.dumps(result, indent=2, default=str))
        except Exception as exc:  # noqa: BLE001
            typer.secho(f"task wait failed: {exc}", fg=typer.colors.YELLOW)


__all__ = ["app"]
