"""Tests for the LLM-as-judge module."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest


@pytest.fixture
def fake_decisions() -> list[dict[str, Any]]:
    return [
        {
            "id": "d-1",
            "vt_symbol": "AAPL.NASDAQ",
            "ts": datetime(2024, 3, 1),
            "action": "BUY",
            "size_pct": 0.1,
            "confidence": 0.7,
            "rating": "buy",
            "rationale": "earnings beat",
            "token_cost_usd": 0.01,
        },
        {
            "id": "d-2",
            "vt_symbol": "MSFT.NASDAQ",
            "ts": datetime(2024, 3, 2),
            "action": "SELL",
            "size_pct": 0.05,
            "confidence": 0.4,
            "rating": "sell",
            "rationale": "guidance cut",
            "token_cost_usd": 0.01,
        },
    ]


def test_judge_report_round_trips() -> None:
    from aqp.backtest.llm_judge import Finding, JudgeReport

    rep = JudgeReport(
        judge_class="LLMJudge",
        backtest_id="bt-1",
        score=0.6,
        summary="ok",
        findings=[
            Finding(
                decision_id="d-1",
                vt_symbol="AAPL.NASDAQ",
                ts="2024-03-01T00:00:00",
                severity="warn",
                verdict="edit",
                recommended_action="HOLD",
                recommended_size_pct=0.0,
                rationale="too aggressive",
            )
        ],
        cost_usd=0.05,
        provider="ollama",
        model="llama3.1",
    )
    payload = rep.to_json_dict()
    assert payload["score"] == 0.6
    assert payload["findings"][0]["verdict"] == "edit"


def test_finding_normalises_bad_inputs() -> None:
    from aqp.backtest.llm_judge import Finding

    f = Finding(
        decision_id="d-1",
        severity="CRITICAL",  # Not in allowed set -> falls back to info
        verdict="garbage",  # -> keep
        recommended_action="long",  # -> HOLD
    )
    assert f.severity == "info"
    assert f.verdict == "keep"
    assert f.recommended_action == "HOLD"


def test_llm_judge_evaluate_with_mocked_complete(
    monkeypatch: pytest.MonkeyPatch,
    fake_decisions: list[dict[str, Any]],
) -> None:
    from aqp.backtest import llm_judge as judge_mod

    class _FakeResult:
        content = (
            '{"score": 0.5, "summary": "looks reasonable",'
            ' "findings": ['
            '{"decision_id": "d-1", "vt_symbol": "AAPL.NASDAQ",'
            ' "ts": "2024-03-01", "severity": "info", "verdict": "keep",'
            ' "recommended_action": "BUY", "recommended_size_pct": 0.1,'
            ' "rationale": "consistent"}'
            "]}"
        )
        provider = "ollama"
        model = "llama3.1"
        cost_usd = 0.04

    def fake_complete(*args: Any, **kwargs: Any) -> _FakeResult:
        return _FakeResult()

    monkeypatch.setattr(judge_mod, "complete", fake_complete)

    judge = judge_mod.LLMJudge(tier="quick", cost_budget_usd=10.0)
    report = judge.evaluate(fake_decisions, backtest_id="bt-1")
    assert report.judge_class == "LLMJudge"
    assert report.backtest_id == "bt-1"
    assert 0.0 <= report.score <= 1.0
    assert len(report.findings) == 1
    assert report.findings[0].decision_id == "d-1"
    assert report.cost_usd > 0


def test_llm_judge_handles_empty_decisions() -> None:
    from aqp.backtest.llm_judge import LLMJudge

    judge = LLMJudge()
    report = judge.evaluate([], backtest_id="bt-empty")
    assert report.findings == []
    assert "No decisions" in report.summary
