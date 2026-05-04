"""Component registry introspection API.

Exposes the in-memory ``aqp.core.registry`` so the Next.js wizard can
hydrate dropdowns of every registered component (universe, alpha,
portfolio, risk, execution, agent, judge, model, env, …) and render
auto-generated forms from each class's constructor signature.

Endpoints
---------

- ``GET /registry/kinds`` — every populated component-kind.
- ``GET /registry/{kind}`` — every alias under that kind, with the
  introspected constructor parameter schema.
- ``GET /registry/{kind}/{alias}`` — single component detail with the
  full docstring.

The route force-imports every registry-populating package on module
load so the registry is fully populated before the first request hits.
"""
from __future__ import annotations

import contextlib
import inspect
import logging
import typing
from typing import Any, get_args, get_origin

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/registry", tags=["registry"])


def _ensure_registry_populated() -> None:
    """Force-import every package whose decorators populate the registry.

    Best-effort: optional dependencies (``xgboost``, ``torch``,
    ``stable_baselines3``…) may not be available in every install, so
    we swallow ``ImportError`` per-import and keep going.
    """
    modules = [
        "aqp.strategies",
        "aqp.strategies.agentic",
        "aqp.strategies.portfolio",
        "aqp.strategies.execution",
        "aqp.strategies.risk_models",
        "aqp.strategies.universes",
        "aqp.agents.financial",
        "aqp.agents.screening",
        "aqp.agents.trading",
        "aqp.ml",
        "aqp.ml.models",
        "aqp.rl",
        "aqp.rl.envs",
        "aqp.rl.agents",
        "aqp.backtest",
        "aqp.backtest.llm_judge",
        "aqp.data",
        "aqp.data.indicators_zoo",
    ]
    for mod_name in modules:
        with contextlib.suppress(Exception):
            __import__(mod_name)


_ensure_registry_populated()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ParamSchema(BaseModel):
    """One constructor parameter."""

    name: str
    annotation: str = Field(default="Any")
    type: str = Field(default="any", description="Coarse JSON-schema type tag")
    default: Any = None
    required: bool = False
    enum: list[Any] | None = None
    description: str | None = None


class ComponentSummary(BaseModel):
    alias: str
    qualname: str
    kind: str
    module: str | None = None
    source: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    doc: str | None = None
    params: list[ParamSchema] = Field(default_factory=list)


class ComponentDetail(ComponentSummary):
    full_doc: str | None = None


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------


_TYPE_TAG: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    tuple: "array",
    set: "array",
}


def _coerce_type_tag(annotation: Any) -> str:
    """Map a Python annotation to a coarse JSON-schema-ish tag."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return "any"
    origin = get_origin(annotation)
    if origin is None:
        if isinstance(annotation, type) and annotation in _TYPE_TAG:
            return _TYPE_TAG[annotation]
        return "any"
    if origin in (list, set, tuple, frozenset):
        return "array"
    if origin is dict:
        return "object"
    if origin is typing.Union or str(origin).endswith("UnionType"):
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return _coerce_type_tag(non_none[0])
        return "any"
    if isinstance(origin, type) and origin in _TYPE_TAG:
        return _TYPE_TAG[origin]
    return "any"


def _extract_enum(annotation: Any) -> list[Any] | None:
    """If the annotation is a ``Literal[...]`` or an ``Enum`` subclass, return its values."""
    origin = get_origin(annotation)
    if origin is typing.Literal:
        return list(get_args(annotation))
    try:
        from enum import Enum

        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return [m.value for m in annotation]
    except Exception:
        pass
    return None


def _format_annotation(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty:
        return "Any"
    return str(annotation).replace("typing.", "")


def _is_required(param: inspect.Parameter) -> bool:
    return param.default is inspect.Parameter.empty


def _safe_default(value: Any) -> Any:
    """Return a JSON-safe representation of ``value`` for the ``default`` field."""
    if value is inspect.Parameter.empty:
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe_default(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_default(v) for k, v in value.items()}
    return repr(value)


def _params_for(cls: type) -> list[ParamSchema]:
    """Inspect ``cls.__init__`` and return per-parameter schemas."""
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return []
    out: list[ParamSchema] = []
    for name, param in sig.parameters.items():
        if name in ("self", "args", "kwargs") or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        out.append(
            ParamSchema(
                name=name,
                annotation=_format_annotation(param.annotation),
                type=_coerce_type_tag(param.annotation),
                default=_safe_default(param.default),
                required=_is_required(param),
                enum=_extract_enum(param.annotation),
            )
        )
    return out


def _summary_for(alias: str, cls: type, kind: str) -> ComponentSummary:
    from aqp.core.registry import get_metadata, get_tags

    raw_tags = sorted(get_tags(cls))
    meta = get_metadata(cls)
    source = meta.get("source")
    category = meta.get("category")
    if not source:
        source_tag = next((t for t in raw_tags if t.startswith("source:")), None)
        if source_tag:
            source = source_tag.split(":", 1)[1]
    if not category:
        category_tag = next((t for t in raw_tags if t.startswith("category:")), None)
        if category_tag:
            category = category_tag.split(":", 1)[1]
    return ComponentSummary(
        alias=alias,
        qualname=f"{cls.__module__}.{cls.__name__}",
        kind=kind,
        module=cls.__module__,
        source=source,
        category=category,
        tags=[t for t in raw_tags if not t.startswith("kind:")],
        doc=(inspect.getdoc(cls) or "").split("\n\n", 1)[0] or None,
        params=_params_for(cls),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/kinds")
def list_kinds() -> dict[str, Any]:
    """Return every populated component-kind plus a count of registered classes per kind."""
    from aqp.core.registry import list_by_kind, list_kinds as _list_kinds

    kinds = _list_kinds()
    return {
        "kinds": [
            {"kind": k, "count": len(list_by_kind(k))} for k in kinds
        ],
    }


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


_TAXONOMY: dict[str, Any] = {
    "models": {
        "title": "Machine learning models",
        "groups": {
            "tree": {
                "label": "Gradient boosted trees",
                "members": ["LGBModel", "XGBModel", "CatBoostModel", "DEnsembleModel"],
                "install": "pip install lightgbm xgboost",
                "paradigms": ["supervised", "ensemble"],
            },
            "linear": {
                "label": "Linear / kernel",
                "members": ["LinearModel"],
                "install": "scikit-learn (default)",
                "paradigms": ["supervised"],
            },
            "torch_recurrent": {
                "label": "Recurrent / sequence (torch)",
                "members": [
                    "LSTMModel",
                    "GRUModel",
                    "ALSTMModel",
                    "TCNModel",
                    "VanillaRNNModel",
                    "BidirectionalModel",
                    "RecurrentForecaster",
                ],
                "install": "pip install torch",
                "paradigms": ["supervised", "self_supervised"],
            },
            "torch_attention": {
                "label": "Attention / Transformer (torch)",
                "members": [
                    "TransformerModel",
                    "LocalformerModel",
                    "AttentionAllModel",
                    "Seq2SeqModel",
                ],
                "install": "pip install torch",
                "paradigms": ["supervised"],
            },
            "torch_tabular": {
                "label": "Tabular deep learning",
                "members": ["TabNetModel", "DNNModel", "GeneralPTNN", "TwoPathModel"],
                "install": "pip install torch",
                "paradigms": ["supervised"],
            },
            "torch_advanced": {
                "label": "Specialised deep models",
                "members": [
                    "GATsModel",
                    "HISTModel",
                    "TRAModel",
                    "ADDModel",
                    "ADARNNModel",
                    "TCTSModel",
                    "SFMModel",
                    "SandwichModel",
                    "KRNNModel",
                    "IGMTFModel",
                ],
                "install": "pip install torch",
                "paradigms": ["supervised", "meta_learning"],
            },
        },
    },
    "forecasters": {
        "title": "Time-series forecasting models",
        "groups": {
            "classical": {
                "label": "Classical statistical forecasters",
                "members": ["AutoArimaForecaster", "StatsmodelsForecaster"],
                "install": "pip install -e .[ml]",
                "paradigms": ["supervised", "time_series"],
            },
            "prophet": {
                "label": "Prophet",
                "members": ["ProphetForecaster"],
                "install": "pip install prophet",
                "paradigms": ["supervised", "time_series"],
            },
            "sktime": {
                "label": "sktime adapters",
                "members": ["SktimeForecaster"],
                "install": "pip install sktime",
                "paradigms": ["supervised", "time_series"],
            },
            "ml": {
                "label": "ML alpha forecaster wrappers",
                "members": [
                    "XGBoostAlpha",
                    "LightGBMAlpha",
                    "LSTMAlpha",
                    "GRUAlpha",
                    "TransformerAlpha",
                    "TCNAlpha",
                    "DeployedModelAlpha",
                ],
                "install": "platform default + ml extras",
                "paradigms": ["supervised"],
            },
        },
    },
    "paradigms": {
        "title": "Training paradigms",
        "items": [
            {
                "key": "supervised",
                "label": "Supervised learning",
                "description": "Predict forward returns / target labels from features (DatasetH).",
            },
            {
                "key": "reinforcement",
                "label": "Reinforcement learning",
                "description": "Train a policy through reward maximisation in a gym Env.",
            },
            {
                "key": "imitation",
                "label": "Imitation / behaviour cloning",
                "description": "Learn from expert trajectories instead of reward.",
            },
            {
                "key": "ensemble",
                "label": "Ensembling",
                "description": "Combine multiple base learners (boosting, stacking, voting).",
            },
            {
                "key": "meta_learning",
                "label": "Meta-learning",
                "description": "Learn to adapt across symbols / regimes (TRA, ADARNN, IGMTF).",
            },
            {
                "key": "rlhf",
                "label": "RLHF",
                "description": "Reinforcement learning from human feedback — overlay on SFT models.",
            },
            {
                "key": "self_supervised",
                "label": "Self-supervised pretraining",
                "description": "Mask / reconstruct / contrast on raw price/feature streams.",
            },
            {
                "key": "online_learning",
                "label": "Online / streaming",
                "description": "Per-bar update; no train/test split.",
            },
            {
                "key": "evolutionary",
                "label": "Evolutionary search",
                "description": "ES / NEAT / novelty search over policy weights.",
            },
        ],
    },
    "time_series": {
        "title": "Time-series analysis methods",
        "items": [
            {"key": "arima", "label": "ARIMA / SARIMAX", "module": "aqp.ml.applications.forecaster.auto_arima"},
            {"key": "prophet", "label": "Prophet", "module": "aqp.ml.applications.forecaster.prophet_adapter"},
            {"key": "sktime", "label": "sktime", "module": "aqp.ml.applications.forecaster.sktime_adapter"},
            {"key": "state_space", "label": "State-space (Kalman)", "module": "aqp.ml.applications.forecaster.statsmodels_adapter"},
            {"key": "garch", "label": "GARCH (volatility)", "module": "aqp.ml.applications.forecaster.statsmodels_adapter"},
            {"key": "cointegration", "label": "Cointegration / pairs", "module": "aqp.strategies.pairs_alpha"},
            {"key": "fracdiff", "label": "Hurst / fractional differentiation", "module": "aqp.data.fracdiff"},
            {"key": "wavelet", "label": "Wavelet decomposition", "module": "aqp.core.indicators"},
            {"key": "tsmom", "label": "Time-series momentum", "module": "aqp.strategies.momentum"},
            {"key": "regime", "label": "Regime detection (HMM / clustering)", "module": "aqp.strategies.adaptive_rotation"},
        ],
    },
    "rl_envs": {
        "title": "RL environments",
        "items": [
            {
                "key": "stock_trading",
                "label": "Single-asset stock trading (continuous)",
                "module": "aqp.rl.envs.stock_trading_env",
                "class": "StockTradingEnv",
            },
            {
                "key": "stock_trading_discrete",
                "label": "Single-asset stock trading (discrete actions)",
                "module": "aqp.rl.envs.stock_trading_discrete",
                "class": "StockTradingDiscreteEnv",
            },
            {
                "key": "portfolio_allocation",
                "label": "Multi-asset portfolio allocation",
                "module": "aqp.rl.envs.portfolio_env",
                "class": "PortfolioAllocationEnv",
            },
        ],
    },
    "rl_algos": {
        "title": "RL algorithms",
        "groups": {
            "policy_gradient": {
                "label": "Policy gradient / actor-critic",
                "members": [
                    "ActorCriticAgent",
                    "ActorCriticDuelAgent",
                    "ActorCriticRecurrentAgent",
                ],
                "framework": "in-house",
            },
            "q_family": {
                "label": "Q-learning family",
                "members": [
                    "QLearningAgent",
                    "DoubleQAgent",
                    "DuelQAgent",
                    "RecurrentQAgent",
                    "CuriosityQAgent",
                ],
                "framework": "in-house",
            },
            "evolutionary": {
                "label": "Evolutionary",
                "members": [
                    "EvolutionStrategyAgent",
                    "NeuroEvolutionAgent",
                    "NeuroEvolutionNoveltyAgent",
                ],
                "framework": "in-house",
            },
            "classical": {
                "label": "Classical baselines",
                "members": [
                    "TurtleAgent",
                    "MovingAverageAgent",
                    "ABCDStrategyAgent",
                    "SignalRollingAgent",
                ],
                "framework": "in-house",
            },
            "sb3": {
                "label": "Stable-Baselines3",
                "members": ["SB3Adapter (PPO|A2C|DDPG|TD3|SAC|DQN)"],
                "framework": "stable-baselines3",
            },
            "ensemble": {
                "label": "Ensemble",
                "members": ["EnsembleAgent"],
                "framework": "in-house",
            },
        },
    },
    "rl_applications": {
        "title": "RL applications (one-shot recipes)",
        "items": [
            {"key": "stock_trading", "label": "Single-stock trading", "module": "aqp.rl.applications.stock_trading"},
            {"key": "portfolio_allocation", "label": "Portfolio allocation", "module": "aqp.rl.applications.portfolio_allocation"},
            {"key": "cryptocurrency_trading", "label": "Crypto trading", "module": "aqp.rl.applications.cryptocurrency_trading"},
            {"key": "ensemble_strategy", "label": "Ensemble (DRL + classical)", "module": "aqp.rl.applications.ensemble_strategy"},
            {"key": "imitation_learning", "label": "Imitation learning", "module": "aqp.rl.applications.imitation_learning"},
            {"key": "fundamental_portfolio_drl", "label": "Fundamentals DRL + Markowitz", "module": "aqp.rl.applications.fundamental_portfolio_drl"},
        ],
    },
}


# Taxonomy routes are declared BEFORE ``/{kind}`` / ``/{kind}/{alias}``
# so FastAPI matches the static prefix first; otherwise a request to
# ``/registry/taxonomy/all`` gets captured by the generic two-segment
# component detail route.


@router.get("/taxonomy/all")
def taxonomy_all() -> dict[str, Any]:
    """Return the curated taxonomy plus per-class availability flags."""
    from aqp.core.registry import list_registered

    available = set(list_registered())

    def _annotate_members(members: list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in members:
            stem = m.split(" ", 1)[0]
            out.append(
                {
                    "name": m,
                    "registered": stem in available,
                }
            )
        return out

    payload = {}
    for top_key, top in _TAXONOMY.items():
        copy = dict(top)
        if "groups" in copy:
            new_groups = {}
            for gk, group in copy["groups"].items():
                gnew = dict(group)
                gnew["members"] = _annotate_members(list(group.get("members", [])))
                new_groups[gk] = gnew
            copy["groups"] = new_groups
        payload[top_key] = copy
    return payload


@router.get("/taxonomy/{section}")
def taxonomy_section(section: str) -> dict[str, Any]:
    if section not in _TAXONOMY:
        raise HTTPException(404, f"unknown taxonomy section {section!r}")
    return _TAXONOMY[section]


# Generic component-browsing routes live AFTER the static taxonomy ones
# so FastAPI's static-first matching returns the taxonomy payload when
# the path is ``/registry/taxonomy/...``.


@router.get("/{kind}", response_model=list[ComponentSummary])
def list_components(
    kind: str,
    source: str | None = None,
    category: str | None = None,
    tag: str | None = None,
) -> list[ComponentSummary]:
    from aqp.core.registry import list_by_kind

    bucket = list_by_kind(kind)
    if not bucket:
        return []
    source_norm = source.strip().lower() if source else None
    category_norm = category.strip().lower() if category else None
    tag_norm = tag.strip().lower() if tag else None

    out: list[ComponentSummary] = []
    for alias, cls in sorted(bucket.items()):
        summary = _summary_for(alias, cls, kind)
        if source_norm and (summary.source or "").lower() != source_norm:
            continue
        if category_norm and (summary.category or "").lower() != category_norm:
            continue
        if tag_norm and not any(t.lower() == tag_norm for t in summary.tags):
            continue
        out.append(summary)
    return out


@router.get("/{kind}/{alias}", response_model=ComponentDetail)
def get_component(kind: str, alias: str) -> ComponentDetail:
    from aqp.core.registry import list_by_kind

    bucket = list_by_kind(kind)
    cls = bucket.get(alias)
    if cls is None:
        raise HTTPException(404, f"no component {alias!r} registered under kind={kind!r}")
    summary = _summary_for(alias, cls, kind).model_dump()
    return ComponentDetail(
        **summary,
        full_doc=inspect.getdoc(cls),
    )
