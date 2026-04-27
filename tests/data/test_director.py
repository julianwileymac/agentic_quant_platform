"""Unit tests for the Nemotron-driven Director planner + verifier.

These tests stub out the LLM call so they remain hermetic — no Ollama,
no network. The goal is to lock in:

- happy-path JSON parsing into :class:`IngestionPlan` / :class:`PlannedDataset`.
- identity-plan fallback when the LLM is unreachable / returns garbage.
- verifier ``accept`` / ``retry`` parsing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aqp.data.pipelines.discovery import DiscoveredDataset, DiscoveredMember


def _make_dataset(family: str, member_count: int = 2) -> DiscoveredDataset:
    ds = DiscoveredDataset(family=family)
    for i in range(member_count):
        ds.members.append(
            DiscoveredMember(
                path=f"/data/{family}_{i}.csv",
                archive_path=None,
                format="csv",
                delimiter=",",
                size_bytes=10_000,
                subdir="",
                outer_mtime=0.0,
            )
        )
    ds.total_bytes = 10_000 * member_count
    ds.sample_columns = ["a", "b", "c"]
    return ds


def test_plan_ingestion_parses_director_json(monkeypatch):
    from aqp.data.pipelines import director as director_mod

    canned = {
        "datasets": [
            {
                "family": "hmda_lar",
                "include": True,
                "target_namespace": "aqp_cfpb",
                "target_table": "hmda_lar",
                "expected_min_rows": 100_000,
                "domain_hint": "financial.regulatory.cfpb.hmda",
                "skip_member_paths": ["/data/hmda_lar_1.csv"],
                "notes": "Combined HMDA LAR public files across years.",
            }
        ],
        "skipped_assets": [],
    }
    monkeypatch.setattr(
        director_mod, "_call_llm", lambda system, user: json.dumps(canned)
    )

    datasets = [_make_dataset("hmda_lar", member_count=2)]
    plan = director_mod.plan_ingestion(
        datasets,
        source_path="/host-downloads/cfpb",
        namespace="aqp_cfpb",
        allowed_namespaces=["aqp_cfpb"],
    )

    assert plan.director_used is True
    assert plan.director_error is None
    assert len(plan.datasets) == 1
    p = plan.datasets[0]
    assert p.family == "hmda_lar"
    assert p.target_namespace == "aqp_cfpb"
    assert p.target_table == "hmda_lar"
    assert p.iceberg_identifier == "aqp_cfpb.hmda_lar"
    assert p.expected_min_rows == 100_000
    assert p.domain_hint == "financial.regulatory.cfpb.hmda"
    # skip_member_paths must round-trip and filter out of member_paths
    assert "/data/hmda_lar_1.csv" in p.skip_member_paths
    assert "/data/hmda_lar_1.csv" not in p.member_paths
    assert "/data/hmda_lar_0.csv" in p.member_paths


def test_plan_ingestion_falls_back_when_llm_returns_garbage(monkeypatch):
    from aqp.data.pipelines import director as director_mod

    monkeypatch.setattr(
        director_mod,
        "_call_llm",
        lambda system, user: "lol I am not JSON",
    )

    datasets = [_make_dataset("hmda_lar"), _make_dataset("complaints")]
    plan = director_mod.plan_ingestion(
        datasets,
        source_path="/host-downloads/cfpb",
        namespace="aqp_cfpb",
    )

    assert plan.director_used is False
    assert plan.director_error == "director_response_unparseable"
    families = {d.family for d in plan.datasets}
    assert families == {"hmda_lar", "complaints"}
    for entry in plan.datasets:
        assert entry.target_namespace == "aqp_cfpb"
        assert entry.target_table == entry.family
        assert entry.member_paths  # identity plan keeps every member


def test_plan_ingestion_falls_back_when_llm_raises(monkeypatch):
    from aqp.data.pipelines import director as director_mod

    def _boom(system, user):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(director_mod, "_call_llm", _boom)

    datasets = [_make_dataset("hmda_lar")]
    plan = director_mod.plan_ingestion(
        datasets,
        source_path="/host-downloads/cfpb",
        namespace="aqp_cfpb",
    )
    assert plan.director_used is False
    assert plan.director_error and "llm_call_failed" in plan.director_error
    assert plan.datasets[0].target_table == "hmda_lar"


def test_plan_carries_assets_into_skipped(monkeypatch):
    """The synthetic ``__assets__`` family always lands in ``skipped_assets``."""
    from aqp.data.pipelines import director as director_mod

    monkeypatch.setattr(
        director_mod,
        "_call_llm",
        lambda system, user: json.dumps({"datasets": [], "skipped_assets": []}),
    )

    main = _make_dataset("hmda_lar")
    assets = DiscoveredDataset(family="__assets__")
    assets.notes.append("XML detected; skipped")

    plan = director_mod.plan_ingestion(
        [main, assets],
        source_path="/host-downloads/uspto",
        namespace="aqp_uspto",
    )

    families = {d.family for d in plan.datasets}
    assert families == {"hmda_lar"}
    assert any(s.get("family") == "__assets__" for s in plan.skipped_assets)


def test_verifier_accepts_when_llm_says_so(monkeypatch):
    from aqp.data.pipelines import director as director_mod

    monkeypatch.setattr(
        director_mod,
        "_call_llm",
        lambda system, user: json.dumps(
            {"verdict": "accept", "reason": "row cap intentional", "retry_with": None}
        ),
    )

    planned = director_mod.PlannedDataset(
        family="hmda_lar",
        target_namespace="aqp_cfpb",
        target_table="hmda_lar",
        expected_min_rows=1_000_000,
    )
    actual = {"rows_written": 5_000_000, "files_consumed": 12, "files_skipped": 0}
    settings_payload = {"max_rows_per_dataset": 5_000_000}

    verdict = director_mod.verify_after_materialise(
        planned=planned, actual=actual, ingestion_settings=settings_payload
    )
    assert verdict.verdict == "accept"
    assert verdict.retry_with == {}


def test_parser_extracts_json_from_chain_of_thought(monkeypatch):
    """Nemotron-style reasoning prefix must not break Director JSON parse."""
    from aqp.data.pipelines import director as director_mod

    cot_response = """We need to produce a single JSON object with datasets array
    and skipped_assets array. For each family in brief, decide include true/false,
    target_namespace (choose from allowed list), target_table (snake_case), etc.

    Looking at the brief, the family ``hmda_lar`` has 6 members totalling 28 GB
    spread across yearly subdirs. We should keep it, route to aqp_cfpb namespace.

    Final answer:

    {
        "datasets": [
            {
                "family": "hmda_lar",
                "include": true,
                "target_namespace": "aqp_cfpb",
                "target_table": "hmda_lar",
                "expected_min_rows": 50000,
                "domain_hint": "financial.regulatory.cfpb.hmda",
                "skip_member_paths": [],
                "notes": "Combined HMDA LAR public files."
            }
        ],
        "skipped_assets": []
    }
    """

    monkeypatch.setattr(director_mod, "_call_llm", lambda system, user: cot_response)

    plan = director_mod.plan_ingestion(
        [_make_dataset("hmda_lar", member_count=2)],
        source_path="/host-downloads/cfpb",
        namespace="aqp_cfpb",
    )

    assert plan.director_used is True
    assert plan.director_error is None
    assert len(plan.datasets) == 1
    p = plan.datasets[0]
    assert p.target_table == "hmda_lar"
    assert p.expected_min_rows == 50_000
    assert p.domain_hint == "financial.regulatory.cfpb.hmda"


def test_verifier_retry_with_knobs(monkeypatch):
    from aqp.data.pipelines import director as director_mod

    monkeypatch.setattr(
        director_mod,
        "_call_llm",
        lambda system, user: json.dumps(
            {
                "verdict": "retry",
                "reason": "row cap hit; raise it",
                "retry_with": {
                    "max_rows_per_dataset": 50_000_000,
                    "force_string_columns": True,
                },
            }
        ),
    )

    planned = director_mod.PlannedDataset(
        family="hmda_lar",
        target_namespace="aqp_cfpb",
        target_table="hmda_lar",
        expected_min_rows=20_000_000,
    )
    actual = {"rows_written": 5_000_000, "files_consumed": 1, "files_skipped": 8}
    verdict = director_mod.verify_after_materialise(
        planned=planned, actual=actual, ingestion_settings={"max_rows_per_dataset": 5_000_000}
    )
    assert verdict.verdict == "retry"
    assert verdict.retry_with["max_rows_per_dataset"] == 50_000_000
    assert verdict.retry_with["force_string_columns"] is True
