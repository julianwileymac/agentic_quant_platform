"""Stream-to-stream transforms used by manifests.

Every transform is registered as a ``transform.*`` engine node so the
Manifest Builder UI can pick from them without ad-hoc plumbing.
"""
from __future__ import annotations

from aqp.data.fetchers.transforms.arrow_filter import ArrowFilterTransform
from aqp.data.fetchers.transforms.arrow_join import ArrowJoinTransform
from aqp.data.fetchers.transforms.arrow_rename import ArrowRenameTransform
from aqp.data.fetchers.transforms.arrow_select import ArrowSelectTransform
from aqp.data.fetchers.transforms.dask_groupby import DaskGroupByTransform
from aqp.data.fetchers.transforms.iceberg_partition_strategy import (
    IcebergPartitionStrategyTransform,
)
from aqp.data.fetchers.transforms.ml_preprocessing import (
    MlImputationTransform,
    MlLagFeaturesTransform,
    MlPreprocessingTransform,
    MlPyODOutliersTransform,
    MlRollingFeaturesTransform,
    MlScaleTransform,
    MlSeasonalDecomposeTransform,
    MlTargetEncodeTransform,
    MlWinsorizeTransform,
)
from aqp.data.fetchers.transforms.pandas_apply import PandasApplyTransform
from aqp.data.fetchers.transforms.ray_map import RayMapTransform

__all__ = [
    "ArrowFilterTransform",
    "ArrowJoinTransform",
    "ArrowRenameTransform",
    "ArrowSelectTransform",
    "DaskGroupByTransform",
    "IcebergPartitionStrategyTransform",
    "MlImputationTransform",
    "MlLagFeaturesTransform",
    "MlPreprocessingTransform",
    "MlPyODOutliersTransform",
    "MlRollingFeaturesTransform",
    "MlScaleTransform",
    "MlSeasonalDecomposeTransform",
    "MlTargetEncodeTransform",
    "MlWinsorizeTransform",
    "PandasApplyTransform",
    "RayMapTransform",
]
