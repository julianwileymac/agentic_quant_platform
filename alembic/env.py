"""Alembic migration environment."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, inspect, pool, text

from aqp.config import settings
from aqp.persistence.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.postgres_dsn)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Alembic defaults ``alembic_version.version_num`` to VARCHAR(32). Revision
# slugs such as ``0039_extended_instrument_taxonomy`` exceed that limit.
_ALEMBIC_VERSION_NUM_WIDTH = 128


def _ensure_alembic_version_column_width(connection) -> None:
    """Widen ``alembic_version.version_num`` before long revision slugs are written."""
    if connection.dialect.name != "postgresql":
        return
    if "alembic_version" not in inspect(connection).get_table_names():
        return
    col = next(
        (
            c
            for c in inspect(connection).get_columns("alembic_version")
            if c["name"] == "version_num"
        ),
        None,
    )
    if col is None:
        return
    col_type = col.get("type")
    length = getattr(col_type, "length", None)
    if length is not None and length >= _ALEMBIC_VERSION_NUM_WIDTH:
        return
    connection.execute(
        text(
            f"ALTER TABLE alembic_version "
            f"ALTER COLUMN version_num TYPE VARCHAR({_ALEMBIC_VERSION_NUM_WIDTH})"
        )
    )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            _ensure_alembic_version_column_width(connection)
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
