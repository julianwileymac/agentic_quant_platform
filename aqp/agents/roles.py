"""Factory functions for each named agent role.

Each factory returns a CrewAI ``Agent``. Role-specific prompts live in
``aqp.llm.prompts``. LLM selection follows TradingAgents' dual-tier pattern.
"""
from __future__ import annotations

from typing import Any

from crewai import Agent

from aqp.agents.tools import get_tool
from aqp.llm.ollama_client import get_crewai_llm
from aqp.llm.prompts import (
    BACKTESTER_SYSTEM,
    DATA_SCOUT_SYSTEM,
    EVALUATOR_SYSTEM,
    HYPOTHESIS_DESIGNER_SYSTEM,
    META_AGENT_SYSTEM,
    RISK_CONTROLLER_SYSTEM,
)


def _make_tools(names: list[str]):
    return [get_tool(n) for n in names]


def make_data_scout(llm: Any | None = None) -> Agent:
    return Agent(
        role="Data Scout",
        goal="Discover and validate local datasets for the research question, citing exact file paths.",
        backstory=DATA_SCOUT_SYSTEM,
        tools=_make_tools(["directory_read", "describe_bars", "chroma_search", "duckdb_query"]),
        llm=llm or get_crewai_llm("quick"),
        allow_delegation=False,
        verbose=True,
    )


def make_hypothesis_designer(llm: Any | None = None) -> Agent:
    return Agent(
        role="Hypothesis Designer",
        goal=(
            "Translate the user's idea into a formal, testable strategy YAML "
            "using the Lean-style 5-stage framework."
        ),
        backstory=HYPOTHESIS_DESIGNER_SYSTEM,
        tools=_make_tools(["chroma_search", "memory_recall"]),
        llm=llm or get_crewai_llm("deep"),
        allow_delegation=True,
        verbose=True,
    )


def make_strategy_backtester(llm: Any | None = None) -> Agent:
    return Agent(
        role="Strategy Backtester",
        goal=(
            "Execute the hypothesis through the event-driven backtester and the walk-forward "
            "optimiser; return the run_id and key metrics."
        ),
        backstory=BACKTESTER_SYSTEM,
        tools=_make_tools(["backtest", "walk_forward", "ledger"]),
        llm=llm or get_crewai_llm("quick"),
        allow_delegation=False,
        verbose=True,
    )


def make_risk_controller(llm: Any | None = None) -> Agent:
    return Agent(
        role="Risk Controller",
        goal="Audit the ledger for limit breaches and flag drawdown/concentration risks.",
        backstory=RISK_CONTROLLER_SYSTEM,
        tools=_make_tools(["risk_check", "ledger"]),
        llm=llm or get_crewai_llm("quick"),
        allow_delegation=False,
        verbose=True,
    )


def make_performance_evaluator(llm: Any | None = None) -> Agent:
    return Agent(
        role="Performance Evaluator",
        goal="Produce Sharpe/Sortino/MaxDD plus a Plotly equity-curve JSON; benchmark against SPY.",
        backstory=EVALUATOR_SYSTEM,
        tools=_make_tools(["metrics", "plotly"]),
        llm=llm or get_crewai_llm("quick"),
        allow_delegation=False,
        verbose=True,
    )


def make_meta_agent(llm: Any | None = None) -> Agent:
    return Agent(
        role="Meta-Agent",
        goal=(
            "Audit the full research loop, decide whether to promote the strategy, "
            "and enforce the kill switch when limits are breached."
        ),
        backstory=META_AGENT_SYSTEM,
        tools=_make_tools(["ledger", "risk_check", "kill_switch"]),
        llm=llm or get_crewai_llm("deep"),
        allow_delegation=True,
        verbose=True,
    )
