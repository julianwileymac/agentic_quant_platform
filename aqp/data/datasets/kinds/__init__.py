"""Bundled dataset kinds.

Importing this package triggers the metaclass-driven registration of
the eight built-in :class:`aqp.data.datasets.BaseDataset` subclasses
under their canonical aliases. Lazy / optional imports keep test
runs hermetic when an extra (e.g. pyarrow, redis) isn't installed.
"""
from __future__ import annotations

from aqp.data.datasets.kinds.api import APIDataset
from aqp.data.datasets.kinds.csdi_imputed import CSDIImputedDataset
from aqp.data.datasets.kinds.csv import CSVDataset
from aqp.data.datasets.kinds.external import ExternalDataset
from aqp.data.datasets.kinds.hudi import HudiDataset
from aqp.data.datasets.kinds.iceberg import IcebergDataset
from aqp.data.datasets.kinds.parquet import ParquetDataset
from aqp.data.datasets.kinds.partitioned import PartitionedDataset
from aqp.data.datasets.kinds.pgvector import PgVectorDataset
from aqp.data.datasets.kinds.questdb import QuestDBDataset
from aqp.data.datasets.kinds.redis_kv import RedisKVDataset
from aqp.data.datasets.kinds.sql import SQLDataset

__all__ = [
    "APIDataset",
    "CSDIImputedDataset",
    "CSVDataset",
    "ExternalDataset",
    "HudiDataset",
    "IcebergDataset",
    "ParquetDataset",
    "PartitionedDataset",
    "PgVectorDataset",
    "QuestDBDataset",
    "RedisKVDataset",
    "SQLDataset",
]
