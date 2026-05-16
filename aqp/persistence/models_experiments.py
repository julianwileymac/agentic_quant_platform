"""Experiment + Test umbrella ORM (Phase 1 of the multi-tenant graph expansion).

Both tables sit *above* the existing typed run tables (``ml_experiment_runs``,
``rl_runs``, ``analysis_runs``, ``backtest_runs``, ``bot_deployments``,
``strategy_tests``, ``paper_trading_runs``, ``agent_runs_v2``) so a single
header captures **"what the user was trying"** while the typed rows keep
their domain-specific columns. The existing tables grow a nullable
``experiment_id`` / ``test_id`` FK in
:mod:`alembic.versions.0037_experiment_test_linkage`.

The contract:

- ``experiments`` is the user-driven container. A research hypothesis or
  bot iteration becomes a single ``Experiment`` row. Nested experiments
  (a sweep, a follow-up, an ablation) point at ``parent_experiment_id``.
- ``tests`` are pass/fail-style assertions associated with an experiment
  (e.g. "Sharpe > 1", "tracking error < 5%"). They reference the run
  that produced the artefact through the same ``experiment_id`` FK on
  the run table itself.
- Both inherit :class:`ProjectScopedMixin` so org -> workspace -> project
  ownership flows through automatically. ``lab_id`` is an optional
  separate FK because research labs ``own`` experiments that live
  outside any project (notebook-style exploratory work).

AGENTS.md hard rule 34 (added in this rollout): every new run-producing
flow MUST populate ``experiment_id`` (and ``test_id`` where applicable)
on its run row. Don't add a new ``*_runs`` table without an
``experiment_id`` FK.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import backref, relationship

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# Canonical experiment kinds. Other code may add unseen kinds — the
# column is a free-form string so the registry stays open — but new
# kinds SHOULD pick from this list when possible. This shape mirrors
# AGENTS.md tagging conventions for run-producing flows.
EXPERIMENT_KINDS: tuple[str, ...] = (
    "ml",
    "rl",
    "analysis",
    "backtest",
    "paper",
    "bot",
    "agent",
    "research",
    "hypothesis",
    "optimization",
    "ablation",
    "sweep",
)

EXPERIMENT_STATUSES: tuple[str, ...] = (
    "draft",
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "paused",
)

TEST_KINDS: tuple[str, ...] = (
    "metric_threshold",   # e.g. Sharpe > 1
    "smoke",              # ran without error
    "regression",         # output equals baseline
    "drift",              # distribution within bounds
    "guardrail",          # FinOps / risk
    "manual",             # human reviewer checked
)


class Experiment(Base, ProjectScopedMixin):
    """The user-driven container for one or more typed runs.

    Roles per columns:

    - ``slug`` is the URL-safe handle a user picks; unique per
      ``(project_id, slug)``.
    - ``kind`` picks from :data:`EXPERIMENT_KINDS`.
    - ``status`` flows through :data:`EXPERIMENT_STATUSES`.
    - ``parent_experiment_id`` enables tree-style nesting (a sweep
      contains many ablations).
    - ``lab_id`` is optional: research labs can host experiments that
      live outside any project. Mutually compatible with the
      ``project_id`` carried by the mixin.
    - ``metrics`` is a free-form jsonb summary the umbrella surface
      can index (mirrored from the underlying run's ``metrics`` blob).

    Table is named ``aqp_experiments`` (not ``experiments``) to avoid
    colliding with MLflow's reserved ``experiments`` table in the
    shared Postgres database.
    """

    __tablename__ = "aqp_experiments"

    id = Column(String(36), primary_key=True, default=_uuid)
    slug = Column(String(120), nullable=False, index=True)
    name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    kind = Column(String(32), nullable=False, default="research", index=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    parent_experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Labs can own experiments that don't belong to any single project
    # (notebook-style research, free-roam ideation). When both are set
    # the lab is the secondary container.
    lab_id = Column(
        String(36),
        ForeignKey("labs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metrics = Column(JSON, default=dict)
    meta = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_experiments_project_slug"),
    )


Index("ix_experiments_kind_status", Experiment.kind, Experiment.status)
Index(
    "ix_experiments_workspace_project",
    Experiment.workspace_id,
    Experiment.project_id,
)
Index(
    "ix_experiments_parent_started",
    Experiment.parent_experiment_id,
    Experiment.started_at,
)


class Test(Base, ProjectScopedMixin):
    """A pass/fail-style assertion attached to an experiment.

    A ``Test`` is *not* the typed run itself — it's the rubric the
    experiment is graded against. One typed run can satisfy many tests
    (e.g. "Sharpe > 1" + "Max DD < 10%" + "trades > 50"); one test can
    span many runs through the experiment they share.

    Columns:

    - ``assertion_kind`` picks from :data:`TEST_KINDS`.
    - ``passed`` is the pass/fail verdict; ``NULL`` means "not yet
      evaluated".
    - ``run_ref_table`` / ``run_ref_id`` form an optional weak
      reference into the specific typed run that produced the
      verdict. The umbrella ``experiment_id`` is the strong link.

    Table is named ``aqp_tests`` so it pairs with ``aqp_experiments``
    and stays clear of any pytest-output-collector / `pytest-django`-
    style table named ``tests``.
    """

    __tablename__ = "aqp_tests"

    id = Column(String(36), primary_key=True, default=_uuid)
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug = Column(String(120), nullable=False, index=True)
    name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    assertion_kind = Column(
        String(32), nullable=False, default="metric_threshold", index=True
    )
    passed = Column(Boolean, nullable=True, index=True)
    details = Column(JSON, default=dict)
    # Weak reference to the typed run row that produced the verdict.
    # The umbrella experiment_id is the strong link; this lets the UI
    # deep-link straight to the run page without an extra join.
    run_ref_table = Column(String(64), nullable=True)
    run_ref_id = Column(String(36), nullable=True)
    evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    experiment = relationship(
        "Experiment",
        backref=backref(
            "tests",
            # ``passive_deletes`` tells SQLAlchemy to trust the
            # ondelete=CASCADE FK on the child column rather than
            # issuing a Python-side UPDATE that would violate the
            # NOT NULL FK. The cascade itself happens at the DB layer.
            passive_deletes=True,
            cascade="all, delete-orphan",
        ),
        foreign_keys=[experiment_id],
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "experiment_id", "slug", name="uq_tests_experiment_slug"
        ),
    )


Index("ix_tests_assertion_passed", Test.assertion_kind, Test.passed)


__all__ = [
    "EXPERIMENT_KINDS",
    "EXPERIMENT_STATUSES",
    "Experiment",
    "TEST_KINDS",
    "Test",
]
