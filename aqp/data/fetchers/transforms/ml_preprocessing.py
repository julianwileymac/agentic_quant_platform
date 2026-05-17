"""ML preprocessing nodes for the data engine.

Bridges ``aqp.ml.processors`` into the manifest-driven pipeline runtime
so a ``PipelineManifest`` can chain ``source -> ml_preprocessing -> sink``
just like any other transform.

Two layers of nodes are provided:

1. The umbrella ``transform.ml_preprocessing`` node accepts either an
   inline list of processor specs (``[{class, module_path, kwargs}, ...]``)
   or a saved ``pipeline_recipe_id``. It re-uses
   :func:`aqp.ml.pipeline_recipes.apply_processor_specs` so the data
   pipeline applies the same transformation as the offline ML training
   loop.
2. Specialized convenience nodes (``transform.ml_scale``,
   ``transform.ml_winsorize``, ``transform.ml_lag_features``,
   ``transform.ml_rolling_features``, ``transform.ml_seasonal_decompose``,
   ``transform.ml_pyod_outliers``, ``transform.ml_imputation``,
   ``transform.ml_target_encode``) each map to a single ``Processor``
   subclass for easy palette pickup.

Each node is hermetic with respect to the data-engine interface: it
accepts an iterator of Arrow ``RecordBatch`` slices and yields Arrow
batches of the transformed pandas frame.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, TransformNode
from aqp.data.engine.registry import register_node

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

logger = logging.getLogger(__name__)


def _resolve_recipe(recipe_id: str) -> dict[str, list[dict[str, Any]]]:
    """Pull a saved ``PipelineRecipe`` row and flatten into a single spec list."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models import PipelineRecipe

    with get_session() as session:
        row = session.get(PipelineRecipe, recipe_id)
        if row is None:
            raise ValueError(f"pipeline recipe {recipe_id!r} not found")
        return {
            "shared": list(row.shared_processors or []),
            "infer": list(row.infer_processors or []),
            "learn": list(row.learn_processors or []),
        }


def _apply_processors(
    df: Any, processor_specs: list[dict[str, Any]], *, fit: bool
) -> Any:
    from aqp.ml.pipeline_recipes import apply_processor_specs

    if not processor_specs:
        return df
    return apply_processor_specs(df, processor_specs, fit=fit)


@register_node(
    "transform.ml_preprocessing",
    description=(
        "Apply an aqp.ml preprocessing recipe (inline or saved recipe id) "
        "to every Arrow batch."
    ),
    tags=("ml", "preprocessing"),
)
class MlPreprocessingTransform(TransformNode):
    """Apply a chain of ``aqp.ml.processors.Processor`` instances.

    Parameters
    ----------
    recipe_id:
        Optional ``PipelineRecipe`` UUID. When supplied, the recipe's
        ``shared_processors`` + ``learn_processors`` are concatenated and
        applied in order.
    processors:
        Inline list of ``{class, module_path, kwargs}`` specs. Used when
        ``recipe_id`` is empty or to layer extra processors on top of a
        saved recipe.
    fit:
        If true (default), processors with ``fit_required=True`` are
        fitted on the first batch and applied stateless on subsequent
        batches. Set to false for inference pipelines that already
        carry fitted state on disk.
    """

    def __init__(
        self,
        *,
        recipe_id: str | None = None,
        processors: list[dict[str, Any]] | None = None,
        fit: bool = True,
        **node_kwargs: Any,
    ) -> None:
        super().__init__(**node_kwargs)
        self.recipe_id = recipe_id
        self.processors = list(processors or [])
        self.fit = bool(fit)
        self._resolved_specs: list[dict[str, Any]] | None = None
        self._first_batch_seen = False

    def _resolve(self) -> list[dict[str, Any]]:
        if self._resolved_specs is not None:
            return self._resolved_specs
        specs: list[dict[str, Any]] = []
        if self.recipe_id:
            recipe = _resolve_recipe(self.recipe_id)
            specs.extend(recipe["shared"])
            specs.extend(recipe["learn"])
        specs.extend(self.processors)
        self._resolved_specs = specs
        return specs

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa

        specs = self._resolve()
        if not specs:
            yield from batches
            return
        for batch in batches:
            if batch.num_rows == 0:
                continue
            df = batch.to_pandas()
            try:
                # First batch fits; subsequent batches reuse fitted state
                # by passing ``fit=False`` on the second pass.
                df = _apply_processors(
                    df, specs, fit=self.fit and not self._first_batch_seen
                )
            except Exception:
                logger.exception(
                    "ml_preprocessing batch failed for recipe %s", self.recipe_id
                )
                continue
            self._first_batch_seen = True
            if df is None or len(df) == 0:
                continue
            new_table = pa.Table.from_pandas(df, preserve_index=False)
            yield from new_table.to_batches()


def _make_single_processor_node(
    *,
    node_name: str,
    processor_class: str,
    processor_module: str,
    description: str,
    tags: tuple[str, ...],
):
    """Helper to register a thin wrapper around a single ``Processor`` class."""

    @register_node(node_name, description=description, tags=tags)
    class _SingleProcessorNode(TransformNode):
        def __init__(self, *, kwargs: dict[str, Any] | None = None, **node_kwargs: Any) -> None:
            super().__init__(**node_kwargs)
            self.processor_kwargs = dict(kwargs or {})
            self.processor_class = processor_class
            self.processor_module = processor_module
            self._inner = MlPreprocessingTransform(
                processors=[
                    {
                        "class": processor_class,
                        "module_path": processor_module,
                        "kwargs": self.processor_kwargs,
                    }
                ],
                fit=True,
            )

        def transform(
            self, batches: Iterable[pa.RecordBatch], ctx: NodeContext
        ) -> Iterator[pa.RecordBatch]:
            yield from self._inner.transform(batches, ctx)

    _SingleProcessorNode.__name__ = "MlScaleTransform" if "scale" in node_name else node_name
    return _SingleProcessorNode


# Specialized convenience nodes — each maps onto a Processor subclass.
MlScaleTransform = _make_single_processor_node(
    node_name="transform.ml_scale",
    processor_class="SklearnTransformerProcessor",
    processor_module="aqp.ml.processors",
    description="Scale numeric columns with sklearn StandardScaler / MinMax / Robust.",
    tags=("ml", "scale"),
)
MlWinsorizeTransform = _make_single_processor_node(
    node_name="transform.ml_winsorize",
    processor_class="WinsorizeByQuantile",
    processor_module="aqp.ml.processors",
    description="Clip extreme values by lower/upper quantile (defaults 1%/99%).",
    tags=("ml", "outliers"),
)
MlLagFeaturesTransform = _make_single_processor_node(
    node_name="transform.ml_lag_features",
    processor_class="LagFeatureGenerator",
    processor_module="aqp.ml.processors",
    description="Append lagged copies of selected columns.",
    tags=("ml", "feature-engineering"),
)
MlRollingFeaturesTransform = _make_single_processor_node(
    node_name="transform.ml_rolling_features",
    processor_class="RollingFeatureGenerator",
    processor_module="aqp.ml.processors",
    description="Append rolling-window aggregates of selected columns.",
    tags=("ml", "feature-engineering"),
)
MlSeasonalDecomposeTransform = _make_single_processor_node(
    node_name="transform.ml_seasonal_decompose",
    processor_class="SeasonalDecomposeFeatures",
    processor_module="aqp.ml.processors",
    description="Append STL trend/seasonal/resid features per series.",
    tags=("ml", "timeseries"),
)
MlPyODOutliersTransform = _make_single_processor_node(
    node_name="transform.ml_pyod_outliers",
    processor_class="PyODOutlierFilter",
    processor_module="aqp.ml.processors",
    description="Drop rows flagged as outliers by a PyOD detector.",
    tags=("ml", "anomaly"),
)
MlImputationTransform = _make_single_processor_node(
    node_name="transform.ml_imputation",
    processor_class="Fillna",
    processor_module="aqp.ml.processors",
    description="Fill NaN values column-wise (mean/median/zero/last).",
    tags=("ml", "preprocessing"),
)
MlTargetEncodeTransform = _make_single_processor_node(
    node_name="transform.ml_target_encode",
    processor_class="TargetEncode",
    processor_module="aqp.ml.processors",
    description="Replace high-cardinality categoricals with target-mean encoding.",
    tags=("ml", "encoding"),
)


__all__ = [
    "MlImputationTransform",
    "MlLagFeaturesTransform",
    "MlPyODOutliersTransform",
    "MlPreprocessingTransform",
    "MlRollingFeaturesTransform",
    "MlScaleTransform",
    "MlSeasonalDecomposeTransform",
    "MlTargetEncodeTransform",
    "MlWinsorizeTransform",
]
