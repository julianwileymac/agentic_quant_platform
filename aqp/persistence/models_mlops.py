"""ORM models for the MLOps service initial slice.

Six tables matching :file:`alembic/versions/0081_mlops_skills_and_artifacts.py`:

* ``ml_skills`` + ``ml_skill_versions`` — hash-locked snapshots of
  :class:`aqp_models.spec.MLSkillSpec`.
* ``ml_skill_runs`` — run ledger for :class:`MLSkillRuntime`. Carries
  ``experiment_id`` + ``test_id`` FKs per AGENTS rule 34.
* ``ml_compiled_artifacts`` — ONNX / TensorRT / TorchScript binaries
  with SHA-256 provenance.
* ``ml_cache_entries`` — LRU state mirror so the operator UI can show
  active cache entries across workers.
* ``ml_serving_sessions`` — active continuous-batching sessions +
  halt state.
* ``ml_ood_violations`` — append-only audit of rejected OOD checks.

Per :file:`.cursor/rules/migrations-persistence.mdc`, ORM model files
live in ``aqp/persistence/models_<domain>.py``; ``aqp_models`` does
NOT define ORM classes — it imports them from here when persistence
is available (gracefully degrading when the table isn't there yet).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base, _uuid


class MlSkill(Base, ProjectScopedMixin):
    """Parent row for an :class:`aqp_models.spec.MLSkillSpec` — one per name."""

    __tablename__ = "ml_skills"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(120), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    kind = Column(String(64), nullable=False, default="custom")
    current_version = Column(Integer, nullable=False, default=1)
    annotations = Column(JSON, nullable=True, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    versions = relationship("MlSkillVersion", backref="skill", cascade="all, delete-orphan")


class MlSkillVersion(Base):
    """Hash-locked spec snapshot (mirrors ``agent_spec_versions``)."""

    __tablename__ = "ml_skill_versions"

    id = Column(String(36), primary_key=True, default=_uuid)
    skill_id = Column(
        String(36),
        ForeignKey("ml_skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    spec_hash = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("skill_id", "version", name="uq_ml_skill_versions_skill_version"),
        UniqueConstraint("spec_hash", name="uq_ml_skill_versions_spec_hash"),
    )


class MlSkillRun(Base, ProjectScopedMixin):
    """Run row for one :meth:`MLSkillRuntime.run` invocation.

    Carries ``experiment_id`` + ``test_id`` FKs per AGENTS rule 34 so
    every new run-producing flow is part of the experiments umbrella.
    """

    __tablename__ = "ml_skill_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    skill_name = Column(String(120), nullable=False, index=True)
    skill_spec_version_id = Column(String(36), nullable=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    elapsed_ms = Column(Float, nullable=True)
    step_outputs = Column(JSON, nullable=True, default=list)
    error = Column(Text, nullable=True)
    actor = Column(String(120), nullable=True)
    actor_kind = Column(String(32), nullable=True)
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    test_id = Column(
        String(36),
        ForeignKey("aqp_tests.id", ondelete="SET NULL"),
        nullable=True,
    )


class MlCompiledArtifact(Base, ProjectScopedMixin):
    """ONNX / TensorRT / TorchScript / quantised artefact + provenance."""

    __tablename__ = "ml_compiled_artifacts"

    id = Column(String(36), primary_key=True, default=_uuid)
    base_model_version_id = Column(
        String(36),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target = Column(String(32), nullable=False, index=True)
    artifact_format = Column(String(32), nullable=False)
    artifact_path = Column(String(512), nullable=False)
    artifact_sha256 = Column(String(64), nullable=False, index=True)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    compile_kwargs = Column(JSON, nullable=True, default=dict)
    elapsed_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class MlCacheEntry(Base, ProjectScopedMixin):
    """LRU cache state mirror for the operator UI."""

    __tablename__ = "ml_cache_entries"

    id = Column(String(36), primary_key=True, default=_uuid)
    key = Column(String(255), nullable=False, unique=True, index=True)
    model_class = Column(String(120), nullable=False)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    hits = Column(Integer, nullable=False, default=0)
    last_access = Column(DateTime, nullable=False, default=datetime.utcnow)
    evicted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class MlServingSession(Base, ProjectScopedMixin):
    """Active continuous-batching serving session + kill-switch state."""

    __tablename__ = "ml_serving_sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    model_alias = Column(String(120), nullable=False)
    model_class = Column(String(120), nullable=False)
    max_batch_size = Column(Integer, nullable=False, default=64)
    max_wait_ms = Column(Integer, nullable=False, default=25)
    halted = Column(Boolean, nullable=False, default=False, index=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)


class MlOodViolation(Base, ProjectScopedMixin):
    """Append-only audit of OOD / circuit-breaker rejections."""

    __tablename__ = "ml_ood_violations"

    id = Column(String(36), primary_key=True, default=_uuid)
    rule_name = Column(String(120), nullable=False, index=True)
    skill_step = Column(String(120), nullable=True)
    reason = Column(String(240), nullable=True)
    failures_in_window = Column(Integer, nullable=False, default=0)
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)


__all__ = [
    "MlCacheEntry",
    "MlCompiledArtifact",
    "MlOodViolation",
    "MlServingSession",
    "MlSkill",
    "MlSkillRun",
    "MlSkillVersion",
]
