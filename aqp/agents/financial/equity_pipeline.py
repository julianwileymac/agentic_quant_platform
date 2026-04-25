"""Compose section agents into a single equity research report.

Mirrors the FinRobot equity research module flow: fetch shared
context (price summary, fundamentals, news digest), run section
agents in parallel where independent, then run the
``MajorTakeawaysAgent`` last with all upstream summaries as input.
The deterministic ``valuation_engine`` (DCF + sensitivity) and
``catalyst_analyzer`` (news + calendar mining) feed the agent prompts
with concrete numbers so the LLM never has to invent them.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from aqp.agents.financial.base import FinancialReport
from aqp.agents.financial.catalysts import extract_catalysts, normalise_news_sentiment
from aqp.agents.financial.equity_sections import (
    BaseSectionAgent,
    CompanyOverviewAgent,
    CompetitorAnalysisAgent,
    InvestmentOverviewAgent,
    MajorTakeawaysAgent,
    NewsSummaryAgent,
    RisksAgent,
    TaglineAgent,
    ValuationOverviewAgent,
)
from aqp.agents.financial.sensitivity import dcf_intrinsic_value, sensitivity_grid
from aqp.config import settings

logger = logging.getLogger(__name__)


SECTION_ORDER = [
    "tagline",
    "company_overview",
    "investment_overview",
    "valuation_overview",
    "risks",
    "competitor_analysis",
    "news_summary",
    # major_takeaways runs last with all section summaries as input.
    "major_takeaways",
]

_SECTION_AGENT_MAP: dict[str, type[BaseSectionAgent]] = {
    "tagline": TaglineAgent,
    "company_overview": CompanyOverviewAgent,
    "investment_overview": InvestmentOverviewAgent,
    "valuation_overview": ValuationOverviewAgent,
    "risks": RisksAgent,
    "competitor_analysis": CompetitorAnalysisAgent,
    "news_summary": NewsSummaryAgent,
    "major_takeaways": MajorTakeawaysAgent,
}


class EquityReport(BaseModel):
    """Aggregated section outputs + valuation + catalysts."""

    vt_symbol: str
    as_of: datetime
    peers: list[str] = Field(default_factory=list)
    sections: dict[str, dict[str, Any]] = Field(default_factory=dict)
    valuation: dict[str, Any] = Field(default_factory=dict)
    sensitivity: dict[str, Any] = Field(default_factory=dict)
    catalysts: list[dict[str, Any]] = Field(default_factory=list)
    news_sentiment: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    cost_usd: float = 0.0

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class EquityReportPipeline:
    """Orchestrate the 8 section agents.

    Public entry point: :meth:`run`. The pipeline is deterministic
    given fixed inputs + a deterministic LLM (``temperature=0`` is
    inherited from the BaseFinancialCrew default).
    """

    def __init__(
        self,
        *,
        provider: str | None = None,
        deep_model: str | None = None,
        quick_model: str | None = None,
        sections: list[str] | None = None,
        max_workers: int = 4,
    ) -> None:
        self.provider = provider
        self.deep_model = deep_model
        self.quick_model = quick_model
        self.sections = list(sections or SECTION_ORDER)
        self.max_workers = max(1, int(max_workers))

    # ---------------------------------------------------------- run --

    def run(
        self,
        *,
        vt_symbol: str,
        as_of: datetime | str,
        price_summary: dict[str, Any] | None = None,
        fundamentals: dict[str, Any] | None = None,
        news_digest: list[dict[str, Any]] | None = None,
        peers: list[str] | None = None,
        valuation_inputs: dict[str, Any] | None = None,
        peer_fundamentals: dict[str, Any] | None = None,
        calendar_events: list[dict[str, Any]] | None = None,
    ) -> EquityReport:
        as_of_dt = (
            datetime.fromisoformat(as_of) if isinstance(as_of, str) else as_of
        )

        valuation_block, sensitivity_block = self._compute_valuation(valuation_inputs)
        catalysts = extract_catalysts(
            news=news_digest, calendar_events=calendar_events, as_of=as_of_dt
        )
        sentiment = normalise_news_sentiment(news_digest)

        shared_extras: dict[str, Any] = {
            "valuation_inputs": valuation_block,
            "valuation_sensitivity": sensitivity_block,
            "peer_fundamentals": peer_fundamentals or {},
            "catalysts": catalysts,
            "news_sentiment": sentiment,
        }

        provider = self.provider or settings.llm_provider
        deep_model = self.deep_model or settings.llm_deep_model
        quick_model = self.quick_model or settings.llm_quick_model

        # Sections that don't depend on others: every section except
        # major_takeaways. We run them in a small thread pool to
        # parallelise LLM I/O.
        independent = [s for s in self.sections if s != "major_takeaways"]

        section_outputs: dict[str, FinancialReport] = {}
        usage_calls: list[dict[str, Any]] = []

        def _invoke(section_key: str) -> tuple[str, FinancialReport]:
            cls = _SECTION_AGENT_MAP.get(section_key)
            if cls is None:
                raise KeyError(f"unknown section {section_key!r}")
            agent = cls(provider=provider, model=deep_model)
            tier = "quick" if section_key in {"tagline", "news_summary"} else "deep"
            agent.tier = tier
            if tier == "quick":
                agent.model = quick_model
            else:
                agent.model = deep_model
            return section_key, agent.run(
                ticker=vt_symbol,
                as_of=as_of_dt.isoformat(),
                price_summary=price_summary,
                fundamentals=fundamentals,
                news_digest=news_digest,
                peers=peers,
                extras=shared_extras,
            )

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futs = {pool.submit(_invoke, key): key for key in independent}
            for fut in as_completed(futs):
                key = futs[fut]
                try:
                    sk, report = fut.result()
                except Exception:
                    logger.exception("section %s failed", key)
                    continue
                section_outputs[sk] = report
                usage_calls.append(report.usage or {})

        # Run major_takeaways last with collected section text.
        if "major_takeaways" in self.sections:
            try:
                summaries = {
                    sk: (rep.payload or {}).get("text", "")
                    for sk, rep in section_outputs.items()
                }
                key, rep = _invoke_with_extra(
                    "major_takeaways",
                    extras={**shared_extras, "section_summaries": summaries},
                    provider=provider,
                    deep_model=deep_model,
                    quick_model=quick_model,
                    vt_symbol=vt_symbol,
                    as_of=as_of_dt,
                    price_summary=price_summary,
                    fundamentals=fundamentals,
                    news_digest=news_digest,
                    peers=peers,
                )
                section_outputs[key] = rep
                usage_calls.append(rep.usage or {})
            except Exception:
                logger.exception("section major_takeaways failed")

        total_cost = sum(float(u.get("cost_usd", 0.0) or 0.0) for u in usage_calls)
        usage = {
            "calls": sum(int(u.get("calls", 0) or 0) for u in usage_calls),
            "prompt_tokens": sum(int(u.get("prompt_tokens", 0) or 0) for u in usage_calls),
            "completion_tokens": sum(
                int(u.get("completion_tokens", 0) or 0) for u in usage_calls
            ),
            "cost_usd": float(total_cost),
            "providers": sorted(
                {
                    p
                    for u in usage_calls
                    for p in (u.get("providers") or [])
                    if p
                }
            ),
            "models": sorted(
                {
                    m
                    for u in usage_calls
                    for m in (u.get("models") or [])
                    if m
                }
            ),
        }

        return EquityReport(
            vt_symbol=vt_symbol,
            as_of=as_of_dt,
            peers=list(peers or []),
            sections={
                key: rep.payload or {} for key, rep in section_outputs.items()
            },
            valuation=valuation_block,
            sensitivity=sensitivity_block,
            catalysts=catalysts,
            news_sentiment=sentiment,
            usage=usage,
            cost_usd=float(round(total_cost, 6)),
        )

    # ------------------------------------------------- valuation --

    @staticmethod
    def _compute_valuation(
        inputs: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(valuation_summary, sensitivity_grid)``.

        If ``inputs`` is missing or incomplete we still emit a
        reasonable default so prompts have *something* to anchor on.
        """
        if not inputs:
            return ({}, {})
        try:
            fcf = float(inputs.get("free_cash_flow_t0") or inputs.get("fcf") or 0.0)
            growth = float(inputs.get("growth_rate", 0.05))
            terminal = float(inputs.get("terminal_growth", 0.025))
            discount = float(inputs.get("discount_rate", 0.09))
            horizon = int(inputs.get("horizon_years", 10))
            shares = inputs.get("shares_outstanding")
            net_debt = float(inputs.get("net_debt", 0.0))
            if fcf <= 0:
                return (
                    {"warning": "missing or non-positive free_cash_flow_t0"},
                    {},
                )
            base = dcf_intrinsic_value(
                free_cash_flow_t0=fcf,
                growth_rate=growth,
                terminal_growth=terminal,
                discount_rate=discount,
                horizon_years=horizon,
                shares_outstanding=float(shares) if shares else None,
                net_debt=net_debt,
            )
            grid = sensitivity_grid(
                free_cash_flow_t0=fcf,
                base_growth=growth,
                base_discount=discount,
                terminal_growth=terminal,
                horizon_years=horizon,
                shares_outstanding=float(shares) if shares else None,
                net_debt=net_debt,
            )
            return (base, grid)
        except Exception:
            logger.exception("equity pipeline: valuation compute failed")
            return ({}, {})


def _invoke_with_extra(
    section_key: str,
    *,
    extras: dict[str, Any],
    provider: str,
    deep_model: str,
    quick_model: str,
    vt_symbol: str,
    as_of: datetime,
    price_summary: dict[str, Any] | None,
    fundamentals: dict[str, Any] | None,
    news_digest: list[dict[str, Any]] | None,
    peers: list[str] | None,
) -> tuple[str, FinancialReport]:
    cls = _SECTION_AGENT_MAP[section_key]
    agent = cls(provider=provider, model=deep_model)
    agent.tier = "quick" if section_key in {"tagline", "news_summary"} else "deep"
    agent.model = quick_model if agent.tier == "quick" else deep_model
    return section_key, agent.run(
        ticker=vt_symbol,
        as_of=as_of.isoformat(),
        price_summary=price_summary,
        fundamentals=fundamentals,
        news_digest=news_digest,
        peers=peers,
        extras=extras,
    )


__all__ = ["EquityReport", "EquityReportPipeline", "SECTION_ORDER"]
