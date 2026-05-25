"""Hash-locking + YAML round-trip tests for :class:`MLSkillSpec`."""
from __future__ import annotations

from aqp_models.spec import MLSkillSpec, SkillStep


def _make_spec(threshold: float = 4.0) -> MLSkillSpec:
    return MLSkillSpec(
        name="regime_aware_alpha",
        description="Two-step regime-aware skill",
        kind="regime_aware_alpha",
        steps=[
            SkillStep(
                name="regime_detector",
                interface_kind="classifier",
                model_ref="LGBModel",
                output_alias="regime",
            ),
            SkillStep(
                name="regime_specialised_alpha",
                interface_kind="predictor",
                model_ref="XGBModel",
                output_alias="alpha_score",
                kwargs={"learning_rate": threshold},
            ),
        ],
    )


def test_canonical_hash_is_deterministic() -> None:
    a = _make_spec()
    b = _make_spec()
    assert a.spec_hash() == b.spec_hash()


def test_changing_kwargs_changes_hash() -> None:
    a = _make_spec(threshold=4.0)
    b = _make_spec(threshold=5.0)
    assert a.spec_hash() != b.spec_hash()


def test_yaml_round_trip_preserves_hash() -> None:
    a = _make_spec()
    body = a.to_yaml()
    b = MLSkillSpec.from_yaml_str(body)
    assert a.spec_hash() == b.spec_hash()


def test_workspace_id_excluded_from_hash() -> None:
    a = _make_spec()
    b = _make_spec()
    b.workspace_id = "ws-1"
    b.project_id = "proj-1"
    assert a.spec_hash() == b.spec_hash()


def test_steps_must_be_non_empty() -> None:
    import pytest

    with pytest.raises(Exception):
        MLSkillSpec(
            name="empty",
            kind="custom",
            steps=[],
        )
