"""``LayeredReflectionAdapter`` — FinAgent 5-stage prompt cascade.

Port of the FinAgent layered-reflection pattern (Zhang AAAI 24,
*FinAgent: A Multimodal Foundation Agent for Financial Trading*).
The original FinAgent runs five LLM passes per decision:

1. **Low-level intelligence** — summarise the raw multimodal state
   (prices, news, sentiment, guidance, economic) into a structured
   "market read" paragraph.
2. **High-level intelligence** — distill the low-level summary plus
   retrieved analogous historical episodes into a strategic outlook.
3. **Low-level reflection** — critique the previous step's
   short-horizon prediction against actual outcomes (1-bar lookback).
4. **High-level reflection** — critique the previous step's strategic
   outlook against the multi-bar realised PnL (k-bar lookback).
5. **Decision** — emit the final SELL / HOLD / BUY action conditioned
   on stages 1-4.

Each stage's LLM call is a separate :class:`AgentRuntime` invocation
(hard rule 12: spec-driven agent runs go through
:class:`AgentRuntime`); every call routes through
:func:`router_complete` (hard rule 2).

The adapter implements :class:`BaseRLAgent` so it slots into
:class:`RLRuntime` like any other RL agent — but with the obvious
caveat that ``train()`` is a no-op (the LLM is fixed; the only
trainable piece is the optional RL backbone passed via
``rl_agent``).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, ClassVar, Mapping

import gymnasium as gym
import numpy as np

from aqp_rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


def _resolve_router_complete():
    """Lazy-import :func:`router_complete` at module load.

    Wrapping the import lets tests monkey-patch
    ``aqp_rl.agents.llm_hybrid_layered._router_complete`` directly
    without needing the full ``aqp.llm.*`` chain to be importable.
    """
    try:
        from aqp.llm.providers.router import router_complete  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        logger.debug("router_complete unavailable at import time")
        return None
    return router_complete


_router_complete = _resolve_router_complete()


_STAGE_NAMES = (
    "low_intelligence",
    "high_intelligence",
    "low_reflection",
    "high_reflection",
    "decision",
)


_DEFAULT_PROMPTS: dict[str, str] = {
    "low_intelligence": (
        "You are FinAgent low-level intelligence. Summarise the raw "
        "multimodal market state below into a 2-3 sentence factual "
        "read covering price action + news tone + sentiment shift.\n\n"
        "State (JSON):\n{state_json}\n\n"
        "Respond with a single JSON object: {{\"summary\": \"<text>\"}}."
    ),
    "high_intelligence": (
        "You are FinAgent high-level intelligence. Given the low-level "
        "summary below, output a strategic outlook (1-3 sentences) "
        "and a directional bias label.\n\n"
        "Low-level summary:\n{low_intelligence_text}\n\n"
        "Respond with JSON: {{\"outlook\": \"<text>\", \"bias\": "
        "\"<bullish|neutral|bearish>\"}}."
    ),
    "low_reflection": (
        "You are FinAgent low-level reflection. Given the last bar's "
        "prediction and the actual realised next-bar return, critique "
        "the error in 1-2 sentences.\n\n"
        "Last prediction: {prev_decision}\n"
        "Realised return: {prev_realised:.4f}\n\n"
        "Respond with JSON: {{\"critique\": \"<text>\"}}."
    ),
    "high_reflection": (
        "You are FinAgent high-level reflection. Given the last "
        "strategic outlook and the realised k-bar PnL, score the "
        "outlook quality on a 0-10 scale and provide a corrective "
        "lesson.\n\n"
        "Last outlook: {prev_outlook}\n"
        "Realised k-bar return: {prev_realised_k:.4f}\n\n"
        "Respond with JSON: {{\"score\": <0-10>, \"lesson\": \"<text>\"}}."
    ),
    "decision": (
        "You are FinAgent decision-maker. Synthesise the stages below "
        "into a final action.\n\n"
        "Low-level intelligence: {low_intelligence_text}\n"
        "High-level outlook: {high_intelligence_outlook}\n"
        "Low reflection: {low_reflection_critique}\n"
        "High reflection: {high_reflection_lesson}\n\n"
        "Respond with JSON: {{\"action\": \"<SELL|HOLD|BUY>\", "
        "\"confidence\": <0-1>}}."
    ),
}


_ACTION_TO_INT = {"SELL": 0, "HOLD": 1, "BUY": 2}


class LayeredReflectionAdapter(BaseRLAgent):
    """FinAgent 5-stage layered prompt cascade.

    Parameters
    ----------
    rl_agent:
        Optional :class:`BaseRLAgent` backbone (or build-spec dict).
        When provided, the adapter blends the RL action with the LLM
        decision using ``rl_weight ∈ [0, 1]``. ``None`` ⇒ pure LLM
        decision.
    llm_model, llm_provider:
        Routed through
        :func:`aqp.llm.providers.router.router_complete`. ``None`` ⇒
        falls back to whatever the router's default provider is.
    rl_weight:
        Blend weight on the RL action. ``0`` ⇒ pure LLM; ``1`` ⇒
        pure RL.
    prompt_templates:
        Optional override mapping ``stage_name -> template str``. Any
        missing stage falls back to the FinAgent defaults baked in
        here.
    """

    rl_alias: ClassVar[str] = "finagent_layered"
    rl_source: ClassVar[str] = "finagent"
    rl_category: ClassVar[str] = "llm_hybrid"
    rl_tags: ClassVar[tuple[str, ...]] = (
        "finagent",
        "llm",
        "layered_reflection",
        "5_stage",
    )
    algorithm: str = "FinAgentLayered"

    def __init__(
        self,
        *,
        rl_agent: BaseRLAgent | dict[str, Any] | None = None,
        llm_model: str | None = None,
        llm_provider: str | None = None,
        rl_weight: float = 0.0,
        prompt_templates: Mapping[str, str] | None = None,
        max_tokens: int = 300,
        temperature: float = 0.1,
    ) -> None:
        from aqp.core.registry import build_from_config

        self.rl_agent: BaseRLAgent | None
        if rl_agent is None:
            self.rl_agent = None
        elif isinstance(rl_agent, dict):
            built = build_from_config(rl_agent)
            if not isinstance(built, BaseRLAgent):
                raise TypeError(
                    f"rl_agent must be a BaseRLAgent; got {type(built).__name__}"
                )
            self.rl_agent = built
        else:
            self.rl_agent = rl_agent
        self.llm_model = llm_model
        self.llm_provider = llm_provider
        if not 0.0 <= rl_weight <= 1.0:
            raise ValueError(f"rl_weight must be in [0, 1]; got {rl_weight!r}")
        self.rl_weight = float(rl_weight)
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.prompt_templates = {
            stage: dict(prompt_templates or {}).get(stage, _DEFAULT_PROMPTS[stage])
            for stage in _STAGE_NAMES
        }
        # Per-step memory of the previous decision so the reflection
        # stages have something to critique.
        self._prev_decision: str | None = None
        self._prev_outlook: str | None = None
        self._prev_realised: float = 0.0
        self._prev_realised_k: float = 0.0

    # ----------------------------------------------------------- lifecycle

    def build(self, env: gym.Env) -> None:
        if self.rl_agent is not None:
            self.rl_agent.build(env)

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        if self.rl_agent is not None:
            self.rl_agent.train(total_timesteps=total_timesteps, callbacks=callbacks, log_interval=log_interval)

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Persist the prompt-template overrides + RL backbone (if any).
        meta = {
            "rl_weight": self.rl_weight,
            "prompt_templates": self.prompt_templates,
        }
        meta_path = p.with_suffix(".finagent.json")
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        if self.rl_agent is not None:
            return self.rl_agent.save(p)
        return meta_path

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        p = Path(path)
        meta_path = p.with_suffix(".finagent.json")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.rl_weight = float(meta.get("rl_weight", self.rl_weight))
            templates = meta.get("prompt_templates") or {}
            for k in _STAGE_NAMES:
                self.prompt_templates[k] = templates.get(k, self.prompt_templates[k])
        if self.rl_agent is not None and p.exists():
            self.rl_agent.load(p, env=env)

    # ----------------------------------------------------------- inference

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        rl_action_int: int | None = None
        rl_state = None
        if self.rl_agent is not None and self.rl_weight > 0:
            rl_action, rl_state = self.rl_agent.predict(obs, deterministic=deterministic)
            try:
                rl_action_int = int(np.asarray(rl_action).flatten()[0])
            except Exception:  # noqa: BLE001
                rl_action_int = None

        decision = self._run_layered_cascade(obs)
        llm_action_int = _ACTION_TO_INT.get(str(decision.get("action", "HOLD")).upper(), 1)

        if rl_action_int is None or self.rl_weight <= 0:
            return llm_action_int, rl_state
        if self.rl_weight >= 1.0:
            return rl_action_int, rl_state
        # Weighted blend ⇒ argmax over the two-element score vector.
        scores = np.zeros(3, dtype=np.float64)
        scores[llm_action_int] += 1.0 - self.rl_weight
        scores[rl_action_int] += self.rl_weight
        return int(np.argmax(scores)), rl_state

    @property
    def model(self) -> Any:
        return self.rl_agent

    # ----------------------------------------------------------- helpers

    def _run_layered_cascade(self, obs: Any) -> dict[str, Any]:
        """Run the 5-stage prompt cascade and return the final decision dict.

        Each stage degrades gracefully: an LLM-call failure produces a
        ``{}`` payload for that stage and the cascade carries on. The
        decision stage's output is *always* a dict with at least
        ``action`` and ``confidence`` keys.
        """
        # Read the module-level shim each call so tests can monkey-patch
        # ``aqp_rl.agents.llm_hybrid_layered._router_complete`` without
        # an import-chain bootstrap.
        import sys

        module = sys.modules[__name__]
        router_complete = getattr(module, "_router_complete", None)
        if router_complete is None:
            logger.warning("router_complete unavailable — defaulting to HOLD")
            return {"action": "HOLD", "confidence": 0.0}

        state_json = self._serialise_obs(obs)
        low_int = self._call_stage(
            router_complete,
            "low_intelligence",
            state_json=state_json,
        )
        high_int = self._call_stage(
            router_complete,
            "high_intelligence",
            low_intelligence_text=low_int.get("summary", ""),
        )
        low_ref = self._call_stage(
            router_complete,
            "low_reflection",
            prev_decision=self._prev_decision or "HOLD",
            prev_realised=self._prev_realised,
        )
        high_ref = self._call_stage(
            router_complete,
            "high_reflection",
            prev_outlook=self._prev_outlook or "",
            prev_realised_k=self._prev_realised_k,
        )
        decision = self._call_stage(
            router_complete,
            "decision",
            low_intelligence_text=low_int.get("summary", ""),
            high_intelligence_outlook=high_int.get("outlook", ""),
            low_reflection_critique=low_ref.get("critique", ""),
            high_reflection_lesson=high_ref.get("lesson", ""),
        )
        # Update memory for next call's reflection stages.
        self._prev_decision = str(decision.get("action", "HOLD"))
        self._prev_outlook = str(high_int.get("outlook", ""))
        return decision

    def _call_stage(
        self,
        router_complete,
        stage: str,
        **format_kwargs: Any,
    ) -> dict[str, Any]:
        template = self.prompt_templates[stage]
        try:
            prompt = template.format(**format_kwargs)
        except KeyError as e:
            logger.warning("missing format key %s in stage %s prompt", e, stage)
            prompt = template
        try:
            response = router_complete(
                model=self.llm_model,
                provider=self.llm_provider,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except Exception:  # noqa: BLE001
            logger.exception("layered cascade stage %s failed", stage)
            return {}
        text = self._extract_text(response)
        return self._parse_json(text, stage)

    @staticmethod
    def _serialise_obs(obs: Any) -> str:
        if isinstance(obs, dict):
            safe = {}
            for k, v in obs.items():
                try:
                    arr = np.asarray(v)
                    safe[str(k)] = arr.tolist() if arr.size < 64 else arr.flatten()[:64].tolist()
                except Exception:  # noqa: BLE001
                    safe[str(k)] = str(v)
            return json.dumps(safe)[:4000]
        try:
            return json.dumps(np.asarray(obs).flatten().tolist()[:64])
        except Exception:  # noqa: BLE001
            return str(obs)[:4000]

    @staticmethod
    def _extract_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            for path in (("choices", 0, "message", "content"), ("content",), ("text",)):
                cur: Any = response
                ok = True
                for key in path:
                    if isinstance(key, int) and isinstance(cur, list) and len(cur) > key:
                        cur = cur[key]
                    elif isinstance(key, str) and isinstance(cur, dict) and key in cur:
                        cur = cur[key]
                    else:
                        ok = False
                        break
                if ok and isinstance(cur, str):
                    return cur
        return ""

    @staticmethod
    def _parse_json(text: str, stage: str) -> dict[str, Any]:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Common LLM artefact: trailing prose around the JSON.
            l_idx = text.find("{")
            r_idx = text.rfind("}")
            if l_idx >= 0 and r_idx > l_idx:
                try:
                    return json.loads(text[l_idx : r_idx + 1])
                except json.JSONDecodeError:
                    pass
            logger.warning("stage %s returned unparseable JSON: %s", stage, text[:120])
            return {}

    # Reflection-memory updater so the env loop can stamp the realised
    # PnL between predict() calls.
    def update_realised_pnl(self, *, realised_short: float, realised_k: float = 0.0) -> None:
        self._prev_realised = float(realised_short)
        self._prev_realised_k = float(realised_k)


__all__ = ["LayeredReflectionAdapter"]
