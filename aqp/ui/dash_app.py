"""Dash strategy-monitor application.

Exposes a :func:`create_dash_app` factory so the same app can be:

- mounted into FastAPI at ``/dash`` via ``starlette.middleware.wsgi`` (the
  default for ``aqp api``), or
- run standalone with ``python -m aqp.ui.dash_app`` on its own port (kept
  for backwards compatibility and local development without FastAPI).

It polls the REST API every few seconds and shows a live table + latest
equity curve plus the paper-trading runs.
"""
from __future__ import annotations

import logging
import os

import pandas as pd
from dash import Dash, Input, Output, dash_table, dcc, html

from aqp.ui.api_client import get

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("AQP_API_URL", "http://localhost:8000")


def create_dash_app(
    requests_pathname_prefix: str | None = None,
    title: str = "AQP — Strategy Monitor",
) -> Dash:
    """Build a configured Dash app, optionally with a URL prefix.

    Parameters
    ----------
    requests_pathname_prefix:
        When mounted under FastAPI (e.g. at ``/dash/``), Dash must know its
        public URL prefix so client-side XHRs hit the right path. The WSGI
        middleware strips the mount prefix before forwarding, so
        ``routes_pathname_prefix`` stays ``/`` while
        ``requests_pathname_prefix`` is the full public prefix. When the
        app runs standalone this stays ``None``.
    """
    kwargs: dict = {}
    if requests_pathname_prefix:
        kwargs["requests_pathname_prefix"] = requests_pathname_prefix
        kwargs["routes_pathname_prefix"] = "/"

    app = Dash(__name__, **kwargs)
    app.title = title
    app.layout = html.Div(
        style={"padding": "16px", "fontFamily": "system-ui"},
        children=[
            html.H1("Strategy Monitor"),
            html.P(f"Polling API at {_API_URL} every 5 seconds."),
            dcc.Interval(id="tick", interval=5 * 1000, n_intervals=0),
            html.H2("Recent backtests"),
            dash_table.DataTable(
                id="runs-table",
                style_table={"overflowX": "auto"},
                page_size=10,
            ),
            html.H2("Latest equity curve"),
            dcc.Graph(id="equity-graph"),
            html.H2("Paper / live trading runs"),
            dash_table.DataTable(
                id="paper-table",
                style_table={"overflowX": "auto"},
                page_size=10,
            ),
        ],
    )

    @app.callback(
        Output("runs-table", "data"),
        Output("runs-table", "columns"),
        Output("equity-graph", "figure"),
        Output("paper-table", "data"),
        Output("paper-table", "columns"),
        Input("tick", "n_intervals"),
    )
    def refresh(_n: int):
        try:
            runs = get("/backtest/runs?limit=25") or []
        except Exception:
            runs = []
        df = pd.DataFrame(runs)
        columns = [{"name": c, "id": c} for c in df.columns]
        fig = {"data": [], "layout": {"title": "No runs yet"}}
        if runs:
            latest = runs[0]["id"]
            try:
                plot = get(f"/backtest/runs/{latest}/plot/equity")
                fig = plot
            except Exception:
                pass

        paper_runs: list[dict] = []
        try:
            paper_runs = get("/paper/runs?limit=25") or []
        except Exception:
            logger.debug("paper runs not reachable", exc_info=True)
        paper_df = pd.DataFrame(paper_runs)
        paper_columns = [{"name": c, "id": c} for c in paper_df.columns]

        return (
            df.to_dict(orient="records"),
            columns,
            fig,
            paper_df.to_dict(orient="records"),
            paper_columns,
        )

    return app


# Keep a module-level ``app`` so ``python -m aqp.ui.dash_app`` works.
app = create_dash_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
