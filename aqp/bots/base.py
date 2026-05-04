"""Abstract base class for AQP bots.

:class:`BaseBot` is a thin coordination layer that:

1. Holds an immutable :class:`aqp.bots.spec.BotSpec`.
2. Derives the runtime configs ``backtest`` / ``paper`` need from that
   spec (universe, strategy, engine, brokerage, feed, risk).
3. Delegates execution to the existing entry points
   (:func:`aqp.backtest.runner.run_backtest_from_config`,
   :func:`aqp.trading.runner.build_session_from_config`,
   :class:`aqp.agents.runtime.AgentRuntime`) — never re-implements them.

Subclasses (:class:`TradingBot`, :class:`ResearchBot`) override
:meth:`backtest`, :meth:`paper`, :meth:`chat`, and :meth:`metrics_snapshot`
to gate which methods are valid for their kind.
"""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

from aqp.bots.spec import BotSpec

logger = logging.getLogger(__name__)


class BotMethodNotSupported(NotImplementedError):
    """Raised when a method is invoked on a bot whose kind doesn't support it."""


class BaseBot(ABC):
    """Common surface for every AQP bot.

    Bots are constructed from a :class:`BotSpec` and stay stateless aside
    from the spec snapshot — every long-lived state (deployments, runs,
    paper sessions) is persisted via the existing ORM tables.
    """

    kind: str = "base"

    def __init__(
        self,
        *,
        spec: BotSpec,
        bot_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        if spec.kind != self.kind and self.kind != "base":
            raise ValueError(
                f"{type(self).__name__} expects spec.kind={self.kind!r}, got {spec.kind!r}"
            )
        self.spec = spec
        self.bot_id = bot_id or f"bot-{uuid.uuid4().hex[:10]}"
        self.project_id = project_id

    # ------------------------------------------------------------------ public API

    def backtest(self, *, run_name: str | None = None, **overrides: Any) -> dict[str, Any]:
        """Run a backtest end-to-end. Default impl uses ``run_backtest_from_config``."""
        if self.spec.strategy is None or self.spec.backtest is None:
            raise BotMethodNotSupported(
                f"Bot {self.spec.name!r} (kind={self.spec.kind}) is missing strategy/backtest blocks"
            )
        from aqp.backtest.runner import run_backtest_from_config

        cfg = self._derive_backtest_cfg(overrides=overrides)
        name = run_name or f"bot-{self.spec.slug}-bt"
        logger.info("[bot:%s] backtest run_name=%s", self.spec.slug, name)
        return run_backtest_from_config(cfg, run_name=name)

    def paper(self, *, run_name: str | None = None, **overrides: Any) -> Any:
        """Build a paper session ready to ``await session.run()``."""
        if self.spec.strategy is None:
            raise BotMethodNotSupported(
                f"Bot {self.spec.name!r} cannot paper-trade without a strategy block"
            )
        from aqp.trading.runner import build_session_from_config

        cfg = self._derive_paper_cfg(overrides=overrides)
        if run_name:
            cfg.setdefault("session", {})
            cfg["session"]["run_name"] = run_name
        logger.info("[bot:%s] paper session=%s", self.spec.slug, cfg.get("session", {}).get("run_name"))
        return build_session_from_config(cfg)

    def deploy(self, *, target: str | None = None, **overrides: Any) -> Any:
        """Dispatch a deployment to the configured target.

        Returns the :class:`aqp.bots.deploy.BotDeploymentResult` produced
        by the dispatcher; subclasses can wrap it for extra metadata.
        """
        from aqp.bots.deploy import DeploymentDispatcher

        dispatcher = DeploymentDispatcher()
        return dispatcher.deploy(self, target=target, overrides=overrides)

    @abstractmethod
    def chat(self, prompt: str, *, session_id: str | None = None, **kwargs: Any) -> Any:
        """Conversational entry point.

        Default impl on :class:`TradingBot` raises
        :class:`BotMethodNotSupported`; :class:`ResearchBot` drives the
        configured agent specs through :class:`AgentRuntime`.
        """

    def metrics_snapshot(self, run_summary: dict[str, Any] | None = None) -> dict[str, Any]:
        """Project the latest backtest/paper summary onto the metrics declared on the spec."""
        out: dict[str, Any] = {}
        if not self.spec.metrics:
            return out
        if run_summary:
            for metric in self.spec.metrics:
                value = run_summary.get(metric.name)
                if value is None:
                    continue
                out[metric.name] = {
                    "value": value,
                    "threshold": metric.threshold,
                    "direction": metric.direction,
                    "passed": _check_threshold(value, metric.threshold, metric.direction),
                }
        return out

    # ------------------------------------------------------------------ derivation

    def _derive_backtest_cfg(self, *, overrides: dict[str, Any]) -> dict[str, Any]:
        """Build the dict consumed by :func:`run_backtest_from_config`.

        Layers (in priority order):

        1. Caller-supplied ``overrides``.
        2. ML deployment hints (``ml_models[0].deployment_id`` injected
           into ``strategy.kwargs.alpha_model.kwargs``).
        3. The bot spec's ``strategy`` and ``backtest`` blocks.
        """
        if not isinstance(self.spec.strategy, dict) or not isinstance(self.spec.backtest, dict):
            raise BotMethodNotSupported(f"Bot {self.spec.name!r} is missing strategy/backtest")
        strategy_cfg = _deep_copy(self.spec.strategy)
        backtest_cfg = _deep_copy(self.spec.backtest)

        # Inject ML deployment id (if the spec named one) into the
        # alpha-model kwargs so the runner's ``_deployment_id_from_strategy_cfg``
        # can pick it up. Existing explicit kwargs win.
        if self.spec.ml_models:
            head = self.spec.ml_models[0]
            kwargs = strategy_cfg.setdefault("kwargs", {})
            alpha = kwargs.setdefault("alpha_model", {})
            alpha_kwargs = alpha.setdefault("kwargs", {})
            alpha_kwargs.setdefault("deployment_id", head.deployment_id)

        # Mirror the bot universe onto the strategy when it lacks one and
        # the spec carries an inline list. Lets a "research-only" bot run
        # ad-hoc backtests without a separate universe block.
        if self.spec.universe.symbols:
            kwargs = strategy_cfg.setdefault("kwargs", {})
            uni = kwargs.setdefault("universe_model", {})
            uni.setdefault("class", "StaticUniverse")
            uni.setdefault("module_path", "aqp.strategies.universes")
            uni_kwargs = uni.setdefault("kwargs", {})
            uni_kwargs.setdefault("symbols", list(self.spec.universe.symbols))

        cfg: dict[str, Any] = {
            "strategy": strategy_cfg,
            "backtest": backtest_cfg,
        }
        # Pass-through any data_source override the caller specified.
        if overrides.get("data_source"):
            cfg["data_source"] = overrides["data_source"]
        # Caller-level shallow merges (top-level keys only).
        for key, value in overrides.items():
            if key in {"strategy", "backtest"} and isinstance(value, dict):
                _deep_update(cfg[key], value)
        return cfg

    def _derive_paper_cfg(self, *, overrides: dict[str, Any]) -> dict[str, Any]:
        """Build the dict consumed by :func:`build_session_from_config`."""
        if not isinstance(self.spec.strategy, dict):
            raise BotMethodNotSupported(f"Bot {self.spec.name!r} is missing strategy")
        cfg: dict[str, Any] = {
            "strategy": _deep_copy(self.spec.strategy),
            "session": {
                "run_name": f"bot-{self.spec.slug}",
                "initial_cash": float(self.spec.deployment.initial_cash),
                "heartbeat_seconds": int(self.spec.deployment.heartbeat_seconds),
                "dry_run": bool(self.spec.deployment.dry_run),
                "max_bars": self.spec.deployment.max_bars,
                "universe": list(self.spec.universe.symbols),
            },
        }
        risk = self.spec.risk.to_runner_dict()
        if risk:
            cfg["risk"] = risk

        broker = self.spec.deployment.brokerage
        if isinstance(broker, dict):
            cfg["brokerage"] = broker
        elif isinstance(broker, str) and broker.lower() not in {"", "simulated", "sim"}:
            cfg["brokerage"] = {"class": _broker_class_alias(broker)}

        feed = self.spec.deployment.feed
        if isinstance(feed, dict):
            cfg["feed"] = feed
        elif isinstance(feed, str) and feed.lower() not in {"", "deterministic_replay", "replay"}:
            cfg["feed"] = {"class": _feed_class_alias(feed)}

        # Caller-level shallow merges.
        for key, value in overrides.items():
            if isinstance(value, dict) and key in cfg and isinstance(cfg[key], dict):
                _deep_update(cfg[key], value)
            elif key not in {"strategy"}:
                cfg[key] = value
        return cfg

    # ------------------------------------------------------------------ misc

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} name={self.spec.name!r} slug={self.spec.slug!r}>"


# ----------------------------------------------------------------- factory


def build_bot(
    spec: BotSpec,
    *,
    bot_id: str | None = None,
    project_id: str | None = None,
) -> BaseBot:
    """Construct the right :class:`BaseBot` subclass for ``spec.kind``."""
    from aqp.bots.research_bot import ResearchBot
    from aqp.bots.trading_bot import TradingBot

    if spec.kind == "trading":
        return TradingBot(spec=spec, bot_id=bot_id, project_id=project_id)
    if spec.kind == "research":
        return ResearchBot(spec=spec, bot_id=bot_id, project_id=project_id)
    raise ValueError(f"Unknown BotSpec.kind={spec.kind!r}")


def load_bot_from_spec(spec_or_name: BotSpec | str, **kwargs: Any) -> BaseBot:
    """Resolve a spec by name (via the registry) and build the bot."""
    if isinstance(spec_or_name, BotSpec):
        return build_bot(spec_or_name, **kwargs)
    from aqp.bots.registry import get_bot_spec

    spec = get_bot_spec(spec_or_name)
    return build_bot(spec, **kwargs)


# ----------------------------------------------------------------- helpers


def _deep_copy(value: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(value)


def _deep_update(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_update(dst[key], value)
        else:
            dst[key] = value


def _broker_class_alias(name: str) -> str:
    table = {
        "alpaca": "AlpacaBrokerage",
        "ibkr": "InteractiveBrokersBrokerage",
        "tradier": "TradierBrokerage",
    }
    return table.get(name.lower(), name)


def _feed_class_alias(name: str) -> str:
    table = {
        "alpaca": "AlpacaDataFeed",
        "ibkr": "IBKRDataFeed",
        "rest": "RestPollingFeed",
    }
    return table.get(name.lower(), name)


def _check_threshold(value: Any, threshold: float | None, direction: str) -> bool | None:
    """``direction='max'`` treats threshold as a floor (higher-is-better);
    ``direction='min'`` treats threshold as a ceiling (lower-is-better)."""
    if threshold is None or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if direction == "min":
        return v <= float(threshold)
    if direction == "max":
        return v >= float(threshold)
    return None


__all__ = [
    "BaseBot",
    "BotMethodNotSupported",
    "build_bot",
    "load_bot_from_spec",
]
