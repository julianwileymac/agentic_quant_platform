"""Bootstrap: create data directories and Postgres tables."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from aqp.config import settings

logger = logging.getLogger(__name__)


def ensure_dirs() -> None:
    for p in (
        settings.data_dir,
        settings.parquet_dir,
        settings.parquet_dir / "bars",
        settings.models_dir,
        settings.chroma_dir,
        settings.data_dir / "memory",
        settings.data_dir / "mlflow",
    ):
        Path(p).mkdir(parents=True, exist_ok=True)
        logger.info("ok: %s", p)


def create_schema() -> None:
    from aqp.persistence.db import engine
    from aqp.persistence.models import Base

    Base.metadata.create_all(bind=engine)
    logger.info("Postgres schema applied.")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Bootstrapping AQP…")
    ensure_dirs()
    try:
        create_schema()
    except Exception as e:
        logger.error("DB schema creation failed: %s. Is Postgres up? (`make up`)", e)
        return 1
    logger.info("Bootstrap complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
