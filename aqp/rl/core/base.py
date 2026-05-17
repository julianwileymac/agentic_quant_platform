"""``RLComponent`` metaclass — uniform registration + introspection contract.

Every base class in :mod:`aqp.rl.core` derives from :class:`RLComponent` so
its concrete subclasses are auto-tagged with their ``rl_kind`` (env, reward,
observation, action, termination, policy, agent, data, ensembler,
experiment, trajectory_store) and registered through
:func:`aqp.core.registry.register`.

This lets the UI / API enumerate everything via
``GET /rl/components/{kind}`` without each subclass needing to remember
to decorate itself.
"""
from __future__ import annotations

import logging
from abc import ABCMeta
from typing import Any, ClassVar

from aqp.core.registry import _kind_index, list_by_kind, register

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical RL component kinds (matches :mod:`aqp.api.routes.rl` + UI palette).
# ---------------------------------------------------------------------------

RL_KIND_ENV = "rl_env"
RL_KIND_REWARD = "rl_reward"
RL_KIND_OBSERVATION = "rl_observation"
RL_KIND_ACTION = "rl_action"
RL_KIND_TERMINATION = "rl_termination"
RL_KIND_POLICY = "rl_policy"
RL_KIND_AGENT = "rl_agent"
RL_KIND_DATA = "rl_data"
RL_KIND_ENSEMBLER = "rl_ensembler"
RL_KIND_EXPERIMENT = "rl_experiment"
RL_KIND_TRAJECTORY_STORE = "rl_trajectory_store"
# Phase 2 (hybrid agentic-RL rollout): the advantage estimator is a
# first-class RL component now. AQP's native ``ReinforcePlusPlusAdvantage``
# (NeMo-RL port) + ``GRPOAdvantage`` (group-relative) register via this
# kind. Surfaces in the RL Lab UI palette + ``GET /rl/components/{kind}``
# alongside envs / rewards / policies.
RL_KIND_ADVANTAGE = "rl_advantage_estimator"
# Phase 3 (hybrid agentic-RL rollout): policy backbones (Transformer,
# RNN, Autoencoder, PatchTST) register via this kind so the spec's
# ``agent.policy_backbone`` field can pick one by alias and the
# SB3/CleanRL adapters can inject it as a custom features-extractor.
RL_KIND_POLICY_BACKBONE = "rl_policy_backbone"

RL_KINDS: tuple[str, ...] = (
    RL_KIND_ENV,
    RL_KIND_REWARD,
    RL_KIND_OBSERVATION,
    RL_KIND_ACTION,
    RL_KIND_TERMINATION,
    RL_KIND_POLICY,
    RL_KIND_AGENT,
    RL_KIND_DATA,
    RL_KIND_ENSEMBLER,
    RL_KIND_EXPERIMENT,
    RL_KIND_TRAJECTORY_STORE,
    RL_KIND_ADVANTAGE,
    RL_KIND_POLICY_BACKBONE,
)


class RLComponentMeta(ABCMeta):
    """Metaclass that auto-registers concrete RLComponent subclasses.

    Subclasses opt in by setting the ``rl_kind`` class attribute (or by
    inheriting from one of the kind-specific base classes in this
    package — :class:`BaseRLEnv`, :class:`BaseRewardModel`, etc.). The
    metaclass:

    1. Resolves ``rl_alias`` (defaults to the class name) and
       ``rl_kind`` (inherited from the closest ancestor).
    2. Calls :func:`aqp.core.registry.register` so the class is browseable
       via ``list_by_kind``, ``list_by_tag`` and ``build_from_config``.
    3. Stamps default tags (``inspiration:<source>``, ``family:<group>``)
       when present so the UI's faceted browsers light up.

    Abstract bases (``__abstract_rl__ = True`` or names starting with
    ``Base``) are skipped — only concrete leaf classes register.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_rl__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        rl_kind = getattr(cls, "rl_kind", None)
        if not rl_kind:
            return cls
        alias = getattr(cls, "rl_alias", None) or cls.__name__
        tags = tuple(getattr(cls, "rl_tags", ()) or ())
        source = getattr(cls, "rl_source", None)
        category = getattr(cls, "rl_category", None)
        try:
            register(
                name=alias,
                kind=rl_kind,
                tags=tags,
                source=source,
                category=category,
            )(cls)
        except Exception:  # noqa: BLE001
            logger.debug("RLComponent auto-registration failed for %s", name, exc_info=True)
        return cls


class RLComponent(metaclass=RLComponentMeta):
    """Abstract root for every registered RL component.

    Subclasses set the following class attributes:

    - ``rl_kind`` (str): canonical kind tag from :data:`RL_KINDS`.
    - ``rl_alias`` (str, optional): registry alias, defaults to the
      class name.
    - ``rl_tags`` (tuple[str, ...], optional): extra tags surfaced in
      registry filters (e.g. ``("finrl", "portfolio")``).
    - ``rl_source`` (str, optional): inspiration source repo
      (``"finrl"``, ``"finrobot"``, ``"aqp"``).
    - ``rl_category`` (str, optional): faceted category tag
      (``"continuous"``, ``"discrete"``, ``"covariance"``…).

    The :class:`RLComponentMeta` metaclass turns these into a
    ``register(name=alias, kind=rl_kind, tags=rl_tags, source=rl_source,
    category=rl_category)`` call at class-definition time.
    """

    __abstract_rl__: ClassVar[bool] = True

    rl_kind: ClassVar[str | None] = None
    rl_alias: ClassVar[str | None] = None
    rl_tags: ClassVar[tuple[str, ...]] = ()
    rl_source: ClassVar[str | None] = None
    rl_category: ClassVar[str | None] = None

    @classmethod
    def describe(cls) -> dict[str, Any]:
        """Return a JSON-friendly summary of the registered component.

        Used by ``GET /rl/components/{kind}`` and the UI library tile.
        """
        return {
            "alias": cls.rl_alias or cls.__name__,
            "kind": cls.rl_kind,
            "module": cls.__module__,
            "class": cls.__name__,
            "tags": list(cls.rl_tags or ()),
            "source": cls.rl_source,
            "category": cls.rl_category,
            "doc": (cls.__doc__ or "").strip().split("\n", 1)[0],
        }


def rl_kind_for(cls: type) -> str | None:
    """Return the ``rl_kind`` declared on ``cls`` (or any ancestor)."""
    return getattr(cls, "rl_kind", None)


def list_rl_components(kind: str | None = None) -> dict[str, type]:
    """Return registered RL components as ``{alias: class}``.

    With no argument returns every kind merged; pass one of
    :data:`RL_KINDS` to scope to a single bucket.
    """
    if kind is not None:
        return list_by_kind(kind)
    out: dict[str, type] = {}
    for k in RL_KINDS:
        out.update(_kind_index.get(k, {}))
    return out


__all__ = [
    "RL_KINDS",
    "RL_KIND_ACTION",
    "RL_KIND_ADVANTAGE",
    "RL_KIND_AGENT",
    "RL_KIND_DATA",
    "RL_KIND_ENSEMBLER",
    "RL_KIND_ENV",
    "RL_KIND_EXPERIMENT",
    "RL_KIND_OBSERVATION",
    "RL_KIND_POLICY",
    "RL_KIND_POLICY_BACKBONE",
    "RL_KIND_REWARD",
    "RL_KIND_TERMINATION",
    "RL_KIND_TRAJECTORY_STORE",
    "RLComponent",
    "RLComponentMeta",
    "list_rl_components",
    "rl_kind_for",
]
