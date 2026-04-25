"""Solara multi-page application — the Quant Assistant portal.

.. deprecated:: 0.3.0
    The Solara UI is being replaced by the Next.js webui under ``webui/``
    (port :3000). The new app is the recommended frontend; this module is
    retained during the strangler migration so existing workflows do not
    break. To start the new UI: ``make webui-dev``.

Launch with::

    aqp ui              # legacy
    # or:
    solara run aqp.ui.app --host 0.0.0.0 --port 8765

Navigation is organised into six sidebar sections — Dashboard / Research /
Data / Lab / Execution / Monitor — plus a catch-all "Other" group for
future routes. Section membership lives in each :class:`solara.Route`'s
``data`` dict so adding a page only needs one change here.
"""
from __future__ import annotations

import logging

import solara

logging.getLogger(__name__).warning(
    "aqp.ui (Solara) is deprecated. Prefer the Next.js webui on :3000 (make webui-dev).",
)

from aqp.ui.layout.app_shell import AppShell
from aqp.ui.pages import agentic_wizard as agentic_wizard_page
from aqp.ui.pages import api_playground as api_playground_page
from aqp.ui.pages import backtest as backtest_page
from aqp.ui.pages import chat as chat_page
from aqp.ui.pages import crew_trace as crew_trace_page
from aqp.ui.pages import dash_embed as dash_page
from aqp.ui.pages import dashboard_home as dashboard_page
from aqp.ui.pages import data as data_page
from aqp.ui.pages import data_browser as data_browser_page
from aqp.ui.pages import credentials as credentials_page
from aqp.ui.pages import factor_workbench as factor_workbench_page
from aqp.ui.pages import fred as fred_page
from aqp.ui.pages import gdelt as gdelt_page
from aqp.ui.pages import indicator_builder as indicator_builder_page
from aqp.ui.pages import live_market as live_market_page
from aqp.ui.pages import sec as sec_page
from aqp.ui.pages import sources as sources_page
from aqp.ui.pages import ml_model_detail as ml_model_detail_page
from aqp.ui.pages import ml_training as ml_training_page
from aqp.ui.pages import monte_carlo as monte_carlo_page
from aqp.ui.pages import optimizer as optimizer_page
from aqp.ui.pages import paper_runs as paper_runs_page
from aqp.ui.pages import portfolio as portfolio_page
from aqp.ui.pages import rl as rl_page
from aqp.ui.pages import strategy as strategy_page
from aqp.ui.pages import strategy_browser as strategy_browser_page


def _route(
    path: str,
    *,
    component,
    label: str,
    section: str,
    glyph: str = "",
) -> solara.Route:
    """Helper to attach section metadata consistently.

    Solara's ``Route`` has an arbitrary ``data`` dict we reuse for the
    sidebar grouping. ``glyph`` is a short unicode icon that the sidebar
    renders in the link row.
    """
    return solara.Route(
        path=path,
        component=component,
        label=label,
        data={"section": section, "glyph": glyph},
    )


routes = [
    _route("/", component=dashboard_page.Page, label="Dashboard", section="home", glyph="🧭"),
    # --- Research ---
    _route("chat", component=chat_page.Page, label="Chat", section="research", glyph="💬"),
    _route(
        "strategy-browser",
        component=strategy_browser_page.Page,
        label="Strategy Browser",
        section="research",
        glyph="📚",
    ),
    _route(
        "indicators",
        component=indicator_builder_page.Page,
        label="Indicator Builder",
        section="research",
        glyph="🎛️",
    ),
    _route(
        "factor-workbench",
        component=factor_workbench_page.Page,
        label="Factor Workbench",
        section="research",
        glyph="🧪",
    ),
    # --- Data ---
    _route("data", component=data_page.Page, label="Data Explorer", section="data", glyph="📦"),
    _route(
        "data-browser",
        component=data_browser_page.Page,
        label="Data Browser",
        section="data",
        glyph="🔎",
    ),
    _route("live", component=live_market_page.Page, label="Live Market", section="data", glyph="📈"),
    _route(
        "sources",
        component=sources_page.Page,
        label="Sources",
        section="data",
        glyph="🔌",
    ),
    _route(
        "credentials",
        component=credentials_page.Page,
        label="Credentials",
        section="data",
        glyph="🔐",
    ),
    _route("fred", component=fred_page.Page, label="FRED", section="data", glyph="🏦"),
    _route("sec", component=sec_page.Page, label="SEC EDGAR", section="data", glyph="📑"),
    _route("gdelt", component=gdelt_page.Page, label="GDelt", section="data", glyph="🌐"),
    # --- Lab ---
    _route(
        "strategy",
        component=strategy_page.Page,
        label="Strategy Workbench",
        section="lab",
        glyph="🛠️",
    ),
    _route("backtest", component=backtest_page.Page, label="Backtest Lab", section="lab", glyph="⚙️"),
    _route(
        "agentic-wizard",
        component=agentic_wizard_page.Page,
        label="Agentic Quickstart",
        section="lab",
        glyph="🧙",
    ),
    _route(
        "optimizer",
        component=optimizer_page.Page,
        label="Optimizer",
        section="lab",
        glyph="🎯",
    ),
    _route(
        "monte-carlo",
        component=monte_carlo_page.Page,
        label="Monte Carlo",
        section="lab",
        glyph="🎲",
    ),
    _route("ml", component=ml_training_page.Page, label="ML Training", section="lab", glyph="🧠"),
    _route(
        "ml-models",
        component=ml_model_detail_page.Page,
        label="ML Models",
        section="lab",
        glyph="🧬",
    ),
    _route("rl", component=rl_page.Page, label="RL Dashboard", section="lab", glyph="🤖"),
    # --- Execution ---
    _route(
        "brokers",
        component=api_playground_page.Page,
        label="API Playground",
        section="execution",
        glyph="🧾",
    ),
    _route(
        "paper",
        component=paper_runs_page.Page,
        label="Paper Runs",
        section="execution",
        glyph="📝",
    ),
    _route(
        "portfolio",
        component=portfolio_page.Page,
        label="Portfolio",
        section="execution",
        glyph="💼",
    ),
    # --- Monitor ---
    _route(
        "monitor",
        component=dash_page.Page,
        label="Strategy Monitor",
        section="monitor",
        glyph="📊",
    ),
    _route(
        "crew",
        component=crew_trace_page.Page,
        label="Crew Trace",
        section="monitor",
        glyph="🧩",
    ),
]


@solara.component
def Page() -> None:
    """Default index component — rendered when someone visits ``/``.

    Solara routes through ``routes`` rather than calling :func:`Page`
    directly for anything but the root, but we still render the dashboard
    here so ``solara run aqp.ui.app`` works without a path argument.
    """
    dashboard_page.Page()


@solara.component
def Layout(children) -> None:
    """Module-level layout Solara picks up for every route.

    We delegate to :class:`AppShell` so every page inherits the same
    grouped sidebar + top bar + breadcrumb chrome.
    """
    AppShell(children=children)
