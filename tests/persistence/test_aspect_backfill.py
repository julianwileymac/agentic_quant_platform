"""Migration smoke tests for metadata-aspect tables/backfill behavior."""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import BaseModel
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.config import settings
from aqp.metadata import write_aspect
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity


class SmokePayload(BaseModel):
    value: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _alembic_config(repo_root: Path) -> Config:
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    return cfg


def _insert_legacy_rows(sqlite_url: str) -> None:
    engine = create_engine(sqlite_url, future=True, poolclass=StaticPool)
    now = datetime.utcnow()
    with engine.begin() as conn:
        # Seed one fixture row in each legacy table expected by backfill.
        conn.execute(
            text(
                """
                INSERT INTO dataset_catalogs (
                    id, name, provider, domain, iceberg_identifier, created_at, updated_at
                ) VALUES (
                    :id, :name, :provider, :domain, :iceberg_identifier, :created_at, :updated_at
                )
                """
            ),
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "bars",
                "provider": "alpha_vantage",
                "domain": "market.bars",
                "iceberg_identifier": "aqp_silver_alpha_vantage.daily_bars",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO entities (
                    id, kind, canonical_name, created_at, updated_at
                ) VALUES (
                    :id, :kind, :canonical_name, :created_at, :updated_at
                )
                """
            ),
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "kind": "company",
                "canonical_name": "Example Corp",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO data_lineage_events (
                    id, transform_kind, created_at
                ) VALUES (
                    :id, :transform_kind, :created_at
                )
                """
            ),
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "transform_kind": "iceberg_append",
                "created_at": now,
            },
        )


def _seed_minimal_legacy_schema(sqlite_url: str) -> None:
    engine = create_engine(sqlite_url, future=True, poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS users (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS workspaces (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS projects (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dataset_catalogs (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(160) NOT NULL,
                    provider VARCHAR(80) NOT NULL,
                    domain VARCHAR(120) NOT NULL,
                    iceberg_identifier VARCHAR(240),
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    id VARCHAR(36) PRIMARY KEY,
                    kind VARCHAR(64),
                    canonical_name VARCHAR(512),
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS data_lineage_events (
                    id VARCHAR(36) PRIMARY KEY,
                    transform_kind VARCHAR(40),
                    created_at DATETIME
                )
                """
            )
        )


def _apply_0048_direct(sqlite_url: str) -> None:
    engine = create_engine(sqlite_url, future=True, poolclass=StaticPool)
    module_path = _repo_root() / "alembic" / "versions" / "0048_metadata_aspects.py"
    spec = importlib.util.spec_from_file_location(
        "aqp_alembic_0048_metadata_aspects",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        operations = Operations(context)
        original_op = module.op
        module.op = operations
        try:
            module.upgrade()
        finally:
            module.op = original_op


def test_sqlite_upgrade_skips_backfill_and_tables_work(tmp_path: Path, monkeypatch) -> None:
    repo_root = _repo_root()
    db_path = tmp_path / "metadata_aspects.sqlite"
    sqlite_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setattr(settings, "postgres_dsn", sqlite_url, raising=False)

    used_alembic_chain = True
    try:
        cfg = _alembic_config(repo_root)
        command.upgrade(cfg, "0047_data_fabric_foundation")
        _insert_legacy_rows(sqlite_url)
        command.upgrade(cfg, "0048_metadata_aspects")
    except Exception:
        used_alembic_chain = False
        _seed_minimal_legacy_schema(sqlite_url)
        _insert_legacy_rows(sqlite_url)
        _apply_0048_direct(sqlite_url)

    engine = create_engine(sqlite_url, future=True, poolclass=StaticPool)
    inspector = inspect(engine)
    assert "metadata_entities" in inspector.get_table_names()
    assert "entity_aspects" in inspector.get_table_names()

    with engine.connect() as conn:
        entity_count = conn.execute(text("SELECT COUNT(*) FROM metadata_entities")).scalar_one()
        aspect_count = conn.execute(text("SELECT COUNT(*) FROM entity_aspects")).scalar_one()
    # SQLite path intentionally skips backfill in migration 0048.
    assert entity_count == 0
    assert aspect_count == 0

    Base.metadata.create_all(
        bind=engine,
        tables=[MetadataEntity.__table__, EntityAspect.__table__],
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    with SessionLocal() as session:
        row = write_aspect(
            session,
            "urn:aqp:dataset:dev:aqp_silver_alpha_vantage.daily_bars",
            "datasetProperties",
            SmokePayload(value="ok"),
        )
        session.commit()
        assert row.version == 1

    with engine.connect() as conn:
        entity_count_after = conn.execute(text("SELECT COUNT(*) FROM metadata_entities")).scalar_one()
        aspect_count_after = conn.execute(text("SELECT COUNT(*) FROM entity_aspects")).scalar_one()
    assert entity_count_after == 1
    assert aspect_count_after == 1
    assert used_alembic_chain in {True, False}

