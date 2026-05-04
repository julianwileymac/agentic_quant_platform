"""Validation, hash determinism, and YAML round-trip for :class:`BotSpec`."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aqp.bots.spec import (
    BotAgentRef,
    BotSpec,
    DeploymentTargetSpec,
    MetricRef,
    MLDeploymentRef,
    RAGRef,
    RiskSpec,
    UniverseRef,
    load_specs_from_dir,
)


def _minimal_trading_spec() -> BotSpec:
    return BotSpec(
        name="Test Trader",
        kind="trading",
        universe=UniverseRef(symbols=["AAPL.NASDAQ"]),
        strategy={"class": "FrameworkAlgorithm", "kwargs": {}},
        backtest={"engine": "vbt-pro:signals", "kwargs": {}},
    )


def test_slug_defaults_from_name() -> None:
    spec = BotSpec(name="My Trading Bot!", kind="trading", strategy={"class": "X"}, backtest={"engine": "x"})
    assert spec.slug == "my-trading-bot"


def test_slug_explicit_takes_precedence() -> None:
    spec = BotSpec(
        name="My Trading Bot",
        slug="custom-slug",
        kind="trading",
        strategy={"class": "X"},
        backtest={"engine": "x"},
    )
    assert spec.slug == "custom-slug"


def test_agents_string_coerces_to_ref() -> None:
    spec = BotSpec(
        name="Spec",
        kind="trading",
        agents=["research.equity"],
        strategy={"class": "X"},
        backtest={"engine": "x"},
    )
    assert len(spec.agents) == 1
    assert isinstance(spec.agents[0], BotAgentRef)
    assert spec.agents[0].spec_name == "research.equity"


def test_metrics_string_coerces_to_ref() -> None:
    spec = BotSpec(
        name="Spec",
        kind="trading",
        metrics=["sharpe", "max_drawdown"],
        strategy={"class": "X"},
        backtest={"engine": "x"},
    )
    assert [m.name for m in spec.metrics] == ["sharpe", "max_drawdown"]
    assert all(isinstance(m, MetricRef) for m in spec.metrics)


def test_rag_dict_coerces_to_singleton_list() -> None:
    spec = BotSpec(
        name="Spec",
        kind="trading",
        rag={"levels": ["l3"], "corpora": ["strategies"]},
        strategy={"class": "X"},
        backtest={"engine": "x"},
    )
    assert len(spec.rag) == 1
    assert isinstance(spec.rag[0], RAGRef)
    assert spec.rag[0].levels == ["l3"]


def test_ml_models_string_coerces_to_ref() -> None:
    spec = BotSpec(
        name="Spec",
        kind="trading",
        ml_models=["dep-123"],
        strategy={"class": "X"},
        backtest={"engine": "x"},
    )
    assert len(spec.ml_models) == 1
    assert isinstance(spec.ml_models[0], MLDeploymentRef)
    assert spec.ml_models[0].deployment_id == "dep-123"


def test_snapshot_hash_deterministic() -> None:
    a = _minimal_trading_spec()
    b = _minimal_trading_spec()
    assert a.snapshot_hash() == b.snapshot_hash()
    assert len(a.snapshot_hash()) == 64


def test_snapshot_hash_changes_on_field_change() -> None:
    a = _minimal_trading_spec()
    b = _minimal_trading_spec()
    b.description = "different"
    assert a.snapshot_hash() != b.snapshot_hash()


def test_to_yaml_round_trip(tmp_path: Path) -> None:
    spec = _minimal_trading_spec()
    yaml_text = spec.to_yaml()
    target = tmp_path / "bot.yaml"
    target.write_text(yaml_text, encoding="utf-8")
    reloaded = BotSpec.from_yaml_path(str(target))
    assert reloaded.snapshot_hash() == spec.snapshot_hash()


def test_universe_symbols_falls_back_to_strategy_kwargs() -> None:
    spec = BotSpec(
        name="Inline-uni",
        kind="trading",
        strategy={
            "class": "FrameworkAlgorithm",
            "kwargs": {
                "universe_model": {
                    "class": "StaticUniverse",
                    "kwargs": {"symbols": ["TSLA.NASDAQ", "NVDA.NASDAQ"]},
                }
            },
        },
        backtest={"engine": "vbt-pro:signals"},
    )
    # No symbols on the spec.universe — should pull from strategy kwargs.
    assert spec.universe_symbols() == ["TSLA.NASDAQ", "NVDA.NASDAQ"]


def test_research_kind_does_not_require_strategy() -> None:
    spec = BotSpec(
        name="Reader",
        kind="research",
        agents=[BotAgentRef(spec_name="research.equity")],
    )
    assert spec.kind == "research"
    assert spec.strategy is None


def test_risk_spec_to_runner_dict() -> None:
    risk = RiskSpec(max_position_pct=0.2, max_daily_loss_pct=0.01)
    out = risk.to_runner_dict()
    assert out["max_position_pct"] == pytest.approx(0.2)
    assert out["max_daily_loss_pct"] == pytest.approx(0.01)
    assert out["max_concentration_pct"] == pytest.approx(0.3)


def test_deployment_target_default_paper_session() -> None:
    dts = DeploymentTargetSpec()
    assert dts.target == "paper_session"
    assert dts.initial_cash == pytest.approx(100000.0)


def test_load_specs_from_dir_recurses(tmp_path: Path) -> None:
    sub = tmp_path / "trading"
    sub.mkdir()
    (sub / "alpha.yaml").write_text(
        yaml.safe_dump(_minimal_trading_spec().model_dump(mode="json")),
        encoding="utf-8",
    )
    specs = list(load_specs_from_dir(str(tmp_path)))
    assert len(specs) == 1
    assert specs[0].slug == "test-trader"


def test_repository_yaml_examples_load() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    examples_dir = repo_root / "configs" / "bots"
    if not examples_dir.exists():
        pytest.skip("configs/bots/ not present in this checkout")
    specs = list(load_specs_from_dir(str(examples_dir)))
    assert specs, "expected at least one example bot spec"
    by_kind = {s.kind for s in specs}
    assert by_kind, "expected at least one bot kind in shipped examples"
