"""Root ``aqp`` Typer CLI.

Consolidates what used to be five separate console-scripts plus bespoke
``make`` targets into a single discoverable surface::

    aqp api
    aqp ui
    aqp worker
    aqp beat
    aqp dash
    aqp paper run --config configs/paper/alpaca_mean_rev.yaml
    aqp backtest run --config configs/strategies/mean_reversion.yaml
    aqp data load --path /mnt/vendor/bars --format csv
    aqp bootstrap
    aqp health
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer
import yaml

from aqp.config import settings

logger = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    help="Agentic Quant Platform — unified command-line interface.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Service launch commands — thin wrappers around existing entrypoints.
# ---------------------------------------------------------------------------


@app.command("api")
def cmd_api(
    host: str = typer.Option(settings.api_host, help="Bind host"),
    port: int = typer.Option(settings.api_port, help="Bind port"),
    reload: bool = typer.Option(settings.api_reload, help="Enable uvicorn reload"),
) -> None:
    """Run the FastAPI gateway (with Dash mounted at /dash)."""
    import uvicorn

    uvicorn.run(
        "aqp.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command("ui")
def cmd_ui(
    host: str = typer.Option(settings.ui_host, help="Bind host"),
    port: int = typer.Option(settings.ui_port, help="Bind port"),
) -> None:
    """Run the Solara multi-page UI."""
    cmd = [sys.executable, "-m", "solara", "run", "aqp.ui.app", "--host", host, "--port", str(port)]
    _exec(cmd)


@app.command("worker")
def cmd_worker(
    queues: str = typer.Option(
        "default,backtest,agents,ingestion,training,paper",
        help="Comma-separated Celery queues",
    ),
    concurrency: int = typer.Option(settings.celery_concurrency, help="Worker concurrency"),
    loglevel: str = typer.Option("info"),
    pool: str = typer.Option(
        "solo" if sys.platform == "win32" else "prefork",
        help="Celery pool (prefork on Linux, solo/threads on Windows to avoid spawn bugs)",
    ),
) -> None:
    """Run a Celery worker."""
    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "aqp.tasks.celery_app",
        "worker",
        f"--loglevel={loglevel}",
        "-Q",
        queues,
        f"--concurrency={concurrency}",
        f"--pool={pool}",
    ]
    _exec(cmd)


@app.command("beat")
def cmd_beat(loglevel: str = typer.Option("info")) -> None:
    """Run Celery Beat."""
    _exec(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "aqp.tasks.celery_app",
            "beat",
            f"--loglevel={loglevel}",
        ]
    )


@app.command("dash")
def cmd_dash(
    mounted: bool = typer.Option(
        True,
        "--mounted/--standalone",
        help="--mounted prints the in-API Dash URL; --standalone launches a dedicated Dash server.",
    ),
    port: int = typer.Option(8050, help="Standalone Dash port"),
) -> None:
    """Run (or report) the Dash visualization engine."""
    if mounted:
        typer.echo(
            f"Dash monitor mounted at {settings.api_url.rstrip('/')}/dash/ (served by `aqp api`)."
        )
        return
    from aqp.ui.dash_app import create_dash_app

    dash_app = create_dash_app()
    dash_app.run(host="0.0.0.0", port=port, debug=False)


@app.command("bootstrap")
def cmd_bootstrap() -> None:
    """Create data dirs and apply DB schema."""
    from scripts.bootstrap import main

    main()


@app.command("health")
def cmd_health() -> None:
    """Query the /health endpoint of a running API."""
    import httpx

    try:
        response = httpx.get(f"{settings.api_url.rstrip('/')}/health", timeout=5.0)
        typer.echo(response.text)
    except Exception as exc:
        typer.echo(f"API not reachable: {exc}", err=True)
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# Serving subcommands (MLflow / Ray / TorchServe).
# ---------------------------------------------------------------------------

try:  # pragma: no cover - import guard for optional serving deps
    from aqp.mlops.serving.cli import app as _serve_app

    app.add_typer(_serve_app, name="serve")
except Exception as _exc:  # pragma: no cover
    logger.debug("serving CLI not available: %s", _exc)


# ---------------------------------------------------------------------------
# Backtest subcommands.
# ---------------------------------------------------------------------------

backtest_app = typer.Typer(help="Run and inspect backtests.", no_args_is_help=True)
app.add_typer(backtest_app, name="backtest")


@backtest_app.command("run")
def backtest_run(
    config: Path = typer.Option(..., "--config", "-c", exists=True, readable=True),
    run_name: str = typer.Option("adhoc"),
    persist: bool = typer.Option(True),
    mlflow: bool = typer.Option(True),
) -> None:
    """Run a backtest from a YAML config file."""
    from aqp.backtest.runner import run_backtest_from_config

    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    result = run_backtest_from_config(cfg, run_name=run_name, persist=persist, mlflow_log=mlflow)
    typer.echo(json.dumps(result, default=str, indent=2))


@backtest_app.command("simulate")
def backtest_simulate(
    config: Path = typer.Option(..., "--config", "-c", exists=True, readable=True),
    local_path: Path = typer.Option(..., "--local-path", "-p", exists=True, readable=True),
    format: str = typer.Option("csv", help="csv | parquet"),
    glob: str | None = typer.Option(None),
    tz: str | None = typer.Option(None),
    start: str | None = typer.Option(None),
    end: str | None = typer.Option(None),
    initial_cash: float = typer.Option(100000.0),
) -> None:
    """Run a strategy against CSV/Parquet files on a mounted drive.

    Uses :class:`aqp.backtest.local_simulation.LocalSimulator`, which
    routes through the exact same event-driven engine as the canonical
    Parquet lake path.
    """
    from aqp.backtest.local_simulation import LocalSimulator
    from aqp.core.registry import build_from_config

    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    strategy_cfg = cfg.get("strategy")
    if strategy_cfg is None:
        raise typer.BadParameter("config must include a 'strategy' block")
    strategy = build_from_config(strategy_cfg)
    simulator = LocalSimulator(
        source_path=local_path,
        format=format,
        glob=glob,
        tz=tz,
    )
    result = simulator.run(
        strategy,
        start=start,
        end=end,
        initial_cash=initial_cash,
    )
    from aqp.backtest.metrics import summarise

    summary = summarise(result.equity_curve, result.trades)
    typer.echo(
        json.dumps(
            {
                "bars": int(len(result.equity_curve)),
                "final_equity": float(result.final_equity),
                "initial_cash": float(result.initial_cash),
                "summary": summary,
            },
            default=str,
            indent=2,
        )
    )


# ---------------------------------------------------------------------------
# Paper trading subcommands.
# ---------------------------------------------------------------------------

paper_app = typer.Typer(help="Paper and live trading.", no_args_is_help=True)
app.add_typer(paper_app, name="paper")


@paper_app.command("run")
def paper_run(
    config: Path = typer.Option(..., "--config", "-c", exists=True, readable=True),
    run_name: str | None = typer.Option(None, help="Override session.run_name"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Force SimulatedBrokerage + replay feed"),
    celery: bool = typer.Option(False, help="Enqueue via Celery instead of blocking in-process"),
) -> None:
    """Run a paper trading session from a YAML config."""
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    if dry_run:
        cfg.setdefault("session", {})["dry_run"] = True
    if celery:
        from aqp.tasks.paper_tasks import run_paper

        async_result = run_paper.delay(cfg, run_name or cfg.get("session", {}).get("run_name", "paper-adhoc"))
        typer.echo(f"Paper session queued: task_id={async_result.id}")
        return
    from aqp.trading.runner import run_paper_session_from_config

    result = run_paper_session_from_config(cfg, run_name=run_name)
    typer.echo(json.dumps(result, default=str, indent=2))


@paper_app.command("stop")
def paper_stop(task_id: str = typer.Argument(...), reason: str = typer.Option("manual")) -> None:
    """Signal a running paper session to drain and exit."""
    from aqp.tasks.paper_tasks import publish_stop_signal

    publish_stop_signal(task_id, reason=reason)
    typer.echo(f"Stop signal sent to {task_id} (reason={reason})")


@paper_app.command("list")
def paper_list(limit: int = typer.Option(20)) -> None:
    """List recent paper runs from the DB."""
    from sqlalchemy import desc, select

    from aqp.persistence.db import get_session
    from aqp.persistence.models import PaperTradingRun

    with get_session() as s:
        rows = s.execute(
            select(PaperTradingRun).order_by(desc(PaperTradingRun.started_at)).limit(limit)
        ).scalars().all()
        for row in rows:
            typer.echo(
                f"{row.id}\t{row.status}\t{row.run_name}\t{row.brokerage}\t"
                f"bars={row.bars_seen}\torders={row.orders_submitted}\tfills={row.fills}"
            )


# ---------------------------------------------------------------------------
# Data subcommands.
# ---------------------------------------------------------------------------

data_app = typer.Typer(help="Ingest and inspect the Parquet lake.", no_args_is_help=True)
app.add_typer(data_app, name="data")


@data_app.command("load")
def data_load(
    path: Path = typer.Option(..., "--path", "-p", exists=True, readable=True),
    format: str = typer.Option("csv", help="csv | parquet"),
    glob: str | None = typer.Option(None, help="File glob pattern (default: *.csv or *.parquet)"),
    mapping: Path | None = typer.Option(
        None, "--mapping", help="Optional YAML file mapping CSV columns → canonical schema"
    ),
    tz: str | None = typer.Option(None, help="Source timezone (converted to UTC on load)"),
    overwrite: bool = typer.Option(False, help="Overwrite existing Parquet in the lake"),
) -> None:
    """Load CSV / Parquet files from a local directory into the Parquet lake."""
    from aqp.data.ingestion import LocalDirectoryLoader

    column_map: dict[str, str] | None = None
    if mapping is not None:
        column_map = yaml.safe_load(mapping.read_text(encoding="utf-8"))
        if not isinstance(column_map, dict):
            raise typer.BadParameter("--mapping must contain a YAML dict")

    loader = LocalDirectoryLoader(
        source_dir=path,
        format=format,
        glob=glob,
        column_map=column_map,
        tz=tz,
    )
    result = loader.run(overwrite=overwrite)
    typer.echo(json.dumps(result, default=str, indent=2))


@data_app.command("ingest")
def data_ingest(
    symbols: str | None = typer.Option(None, help="Comma-separated tickers (defaults to settings.default_universe)"),
    start: str | None = typer.Option(None),
    end: str | None = typer.Option(None),
    interval: str = typer.Option("1d"),
    source: str = typer.Option("auto", help="auto | alpha_vantage | yfinance"),
) -> None:
    """Download bars into the Parquet lake using the configured provider policy."""
    from aqp.data.ingestion import ingest

    tickers = [t.strip() for t in symbols.split(",")] if symbols else None
    df = ingest(symbols=tickers, start=start, end=end, interval=interval, source=source)
    typer.echo(f"Wrote {len(df)} rows across {df['vt_symbol'].nunique() if not df.empty else 0} symbols.")


@data_app.command("describe")
def data_describe() -> None:
    """Print a summary of the Parquet lake."""
    from aqp.data.duckdb_engine import DuckDBHistoryProvider

    df = DuckDBHistoryProvider().describe_bars()
    if df.empty:
        typer.echo("Parquet lake is empty. Run `aqp data ingest` or `aqp data load`.")
        return
    typer.echo(df.to_string(index=False))


# ---------------------------------------------------------------------------
# Data-plane expansion: source registry / FRED / SEC / GDelt subcommands.
# ---------------------------------------------------------------------------


sources_app = typer.Typer(help="Manage the data_sources registry.", no_args_is_help=True)
data_app.add_typer(sources_app, name="sources")


@sources_app.command("list")
def sources_list(enabled_only: bool = typer.Option(False, help="Only show enabled sources")) -> None:
    """List every registered data source."""
    from aqp.data.sources.registry import list_data_sources

    rows = list_data_sources(enabled_only=enabled_only)
    if not rows:
        typer.echo("No data sources registered. Apply the 0007 migration.")
        return
    for row in rows:
        status = "on " if row["enabled"] else "off"
        typer.echo(
            f"{status}  {row['name']:<14}  {row['kind']:<14}  {row['display_name']}"
        )


@sources_app.command("probe")
def sources_probe(name: str = typer.Argument(...)) -> None:
    """Run a health check against a registered adapter."""
    loader_map = {
        "fred": "aqp.data.sources.fred.series:FredSeriesAdapter",
        "sec_edgar": "aqp.data.sources.sec.filings:SecFilingsAdapter",
        "gdelt": "aqp.data.sources.gdelt.adapter:GDeltAdapter",
    }
    spec = loader_map.get(name)
    if spec is None:
        typer.echo(f"No runtime adapter for source {name!r}", err=True)
        raise typer.Exit(code=2)
    module_path, _, class_name = spec.partition(":")
    module = __import__(module_path, fromlist=[class_name])
    adapter = getattr(module, class_name)()
    result = adapter.probe()
    typer.echo(
        json.dumps(
            {"name": name, "ok": bool(result.ok), "message": result.message, "details": result.details},
            default=str,
            indent=2,
        )
    )


@sources_app.command("toggle")
def sources_toggle(
    name: str = typer.Argument(...),
    enabled: bool = typer.Option(True, "--on/--off", help="Enable or disable the source"),
) -> None:
    """Enable or disable a registered source."""
    from aqp.data.sources.registry import set_data_source_enabled

    row = set_data_source_enabled(name, enabled)
    if row is None:
        typer.echo(f"Source {name!r} not found", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{row['name']} → enabled={row['enabled']}")


fred_cli = typer.Typer(help="FRED economic-series helpers.", no_args_is_help=True)
data_app.add_typer(fred_cli, name="fred")


@fred_cli.command("ingest")
def fred_ingest_cli(
    series_ids: list[str] = typer.Argument(..., help="FRED series ids (e.g. DGS10 UNRATE)"),
    start: str | None = typer.Option(None),
    end: str | None = typer.Option(None),
    celery: bool = typer.Option(False, help="Queue through Celery instead of running inline"),
) -> None:
    """Pull observations for one or more FRED series."""
    if celery:
        from aqp.tasks.ingestion_tasks import ingest_fred_series

        async_result = ingest_fred_series.delay(list(series_ids), start, end, None, None)
        typer.echo(f"Queued: task_id={async_result.id}")
        return
    from aqp.data.sources.fred.series import FredSeriesAdapter

    adapter = FredSeriesAdapter()
    output: list[dict[str, Any]] = []
    for series_id in series_ids:
        result = adapter.fetch_observations(series_id=series_id, start=start, end=end)
        output.append({"series_id": series_id, "rows": result.row_count})
    typer.echo(json.dumps(output, indent=2))


sec_cli = typer.Typer(help="SEC EDGAR helpers (requires [sec] extra).", no_args_is_help=True)
data_app.add_typer(sec_cli, name="sec")


@sec_cli.command("ingest")
def sec_ingest_cli(
    cik_or_ticker: str = typer.Argument(...),
    form: str | None = typer.Option(None),
    start: str | None = typer.Option(None),
    end: str | None = typer.Option(None),
    artifact: str | None = typer.Option(None, help="financials | insider | holdings"),
    limit: int = typer.Option(100),
    celery: bool = typer.Option(False),
) -> None:
    """Index SEC filings for a company (optionally fetching parsed artifacts)."""
    artifacts = [artifact] if artifact else []
    if celery:
        from aqp.tasks.ingestion_tasks import ingest_sec_filings

        async_result = ingest_sec_filings.delay(
            cik_or_ticker, form, start, end, artifacts, limit
        )
        typer.echo(f"Queued: task_id={async_result.id}")
        return
    from aqp.data.sources.sec.filings import SecFilingsAdapter

    adapter = SecFilingsAdapter()
    meta = adapter.fetch_metadata(
        cik_or_ticker=cik_or_ticker,
        form=form,
        start=start,
        end=end,
        limit=limit,
    )
    summary: dict[str, Any] = {"filings": meta.get("count"), "artifacts": {}}
    for art in artifacts:
        obs = adapter.fetch_observations(
            cik_or_ticker=cik_or_ticker,
            artifact=art,
            form=form,
            start=start,
            end=end,
        )
        summary["artifacts"][art] = obs.row_count
    typer.echo(json.dumps(summary, indent=2))


gdelt_cli = typer.Typer(help="GDelt GKG 2.0 helpers.", no_args_is_help=True)
data_app.add_typer(gdelt_cli, name="gdelt")


@gdelt_cli.command("ingest")
def gdelt_ingest_cli(
    start: str = typer.Option(..., "--start"),
    end: str = typer.Option(..., "--end"),
    mode: str = typer.Option("manifest", help="manifest | bigquery | hybrid"),
    tickers: str | None = typer.Option(None, help="Comma-separated ticker filter"),
    max_files: int | None = typer.Option(None),
    celery: bool = typer.Option(False),
) -> None:
    """Ingest a GDelt window into the parquet lake (or query BigQuery)."""
    ticker_list = [t.strip().upper() for t in (tickers or "").split(",") if t.strip()] or None
    if celery:
        from aqp.tasks.ingestion_tasks import ingest_gdelt_window

        async_result = ingest_gdelt_window.delay(
            start, end, mode, ticker_list, None, None, max_files
        )
        typer.echo(f"Queued: task_id={async_result.id}")
        return
    from aqp.data.sources.gdelt.adapter import GDeltAdapter

    adapter = GDeltAdapter()
    result = adapter.fetch_observations(
        start=start,
        end=end,
        mode=mode,  # type: ignore[arg-type]
        tickers=ticker_list,
        max_files=max_files,
    )
    typer.echo(json.dumps({"rows": result.row_count, "lineage": result.lineage}, default=str, indent=2))


links_app = typer.Typer(help="Inspect data-availability links.", no_args_is_help=True)
data_app.add_typer(links_app, name="links")


@links_app.command("show")
def links_show(vt_symbol: str = typer.Argument(..., help="e.g. AAPL.NASDAQ")) -> None:
    """Print the data-availability summary for an instrument."""
    from sqlalchemy import func, select

    from aqp.persistence.db import get_session
    from aqp.persistence.models import (
        DataLink,
        DataSource,
        DatasetCatalog,
        DatasetVersion,
        Instrument,
    )

    with get_session() as session:
        instrument = session.execute(
            select(Instrument).where(Instrument.vt_symbol == vt_symbol).limit(1)
        ).scalar_one_or_none()
        if instrument is None:
            typer.echo(f"instrument {vt_symbol} not found", err=True)
            raise typer.Exit(code=1)
        rows = session.execute(
            select(
                DataSource.name,
                DatasetCatalog.domain,
                func.count(DataLink.id),
                func.sum(DataLink.row_count),
            )
            .select_from(DataLink)
            .join(DatasetVersion, DatasetVersion.id == DataLink.dataset_version_id)
            .join(DatasetCatalog, DatasetCatalog.id == DatasetVersion.catalog_id)
            .outerjoin(DataSource, DataSource.id == DataLink.source_id)
            .where(DataLink.instrument_id == instrument.id)
            .group_by(DataSource.name, DatasetCatalog.domain)
            .order_by(DatasetCatalog.domain)
        ).all()
        if not rows:
            typer.echo(f"No data_links rows for {vt_symbol}.")
            return
        for name, domain, count, total_rows in rows:
            typer.echo(
                f"{(name or 'unknown'):<14}  {domain:<22}  datasets={count}  rows={int(total_rows or 0)}"
            )


def _exec(cmd: list[str]) -> None:
    logger.info("exec: %s", " ".join(cmd))
    try:
        completed = subprocess.run(cmd, check=False)
    except FileNotFoundError as exc:
        typer.echo(f"Command not found: {cmd[0]} ({exc})", err=True)
        raise typer.Exit(code=127) from exc
    if completed.returncode != 0:
        raise typer.Exit(code=completed.returncode)


def _main() -> Any:
    return app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
