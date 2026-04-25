"""Index the local Parquet lake into ChromaDB for semantic discovery."""
from __future__ import annotations

import logging
import sys

from aqp.data.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        n = ChromaStore().index_parquet_dir()
    except Exception as e:
        logger.error("Indexing failed: %s", e)
        return 1
    logger.info("Indexed %d parquet files into ChromaDB.", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
