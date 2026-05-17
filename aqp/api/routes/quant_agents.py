"""``/quant-agents/*`` — REST surface for AlphaResearcher + StrategyExecutor.

Phase 4 of the hybrid agentic-RL rollout. Wraps the two driver
classes in :mod:`aqp.agents.quant` with thin REST endpoints so the
Vite frontend can:

- Propose new symbolic alpha factors via
  ``POST /quant-agents/alpha-researcher/propose``.
- Compile + evaluate a proposed formula via
  ``POST /quant-agents/alpha-researcher/evaluate``.
- Test-compile a formula in the AST sandbox without persisting
  anything via ``POST /quant-agents/factor/compile-preview``.
- Dispatch an RL experiment lifecycle action via
  ``POST /quant-agents/strategy-executor/dispatch``.
- List the registered quant-agent specs (alpha_researcher,
  strategy_executor) via ``GET /quant-agents/specs``.

All endpoints respect the canonical AQP boundaries:
- LLM calls go through ``router_complete`` inside
  :class:`AgentRuntime` (rule 2).
- DB reads go through DataMCP tools and the agent runtime (rule 22).
- RL lifecycle actions go through :class:`RLRuntime` (rule 16).
- LLM-emitted formulas go through the AST sandbox in
  :mod:`aqp.data.expressions_dsl` (rule 39).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quant-agents", tags=["quant-agents"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class FactorCompilePreviewRequest(BaseModel):
    formula: str = Field(description="Symbolic alpha formula in the AQP DSL.")
    name: str | None = Field(default=None, description="Optional human-readable alias.")


class FactorCompilePreviewResponse(BaseModel):
    ok: bool
    formula: str
    name: str | None = None
    used_operators: list[str] = Field(default_factory=list)
    used_fields: list[str] = Field(default_factory=list)
    error: str | None = None


class AlphaProposeRequest(BaseModel):
    intent: str = Field(description="Free-form research direction for the agent.")
    vt_symbol: str | None = None
    recent_factor_summary: list[dict[str, Any]] = Field(default_factory=list)
    agent_spec_name: str = Field(default="alpha_researcher")


class AlphaProposeResponse(BaseModel):
    name: str
    formula: str
    rationale: str
    expected_horizon_bars: int | None = None
    expected_direction: str | None = None
    raw_output: dict[str, Any] | None = None


class AlphaEvaluateRequest(BaseModel):
    name: str = Field(default="alpha")
    formula: str = Field(description="Symbolic formula to compile + backtest.")
    rationale: str = ""
    vt_symbols: list[str] | None = None
    sharpe_weight: float = 1.0
    drawdown_weight: float = 0.5
    turnover_weight: float = 0.2


class AlphaEvaluateResponse(BaseModel):
    name: str
    formula: str
    rationale: str
    compiled: bool
    metrics: dict[str, float] = Field(default_factory=dict)
    reward: float = 0.0
    rejection_reason: str | None = None


class StrategyDispatchRequest(BaseModel):
    intent: str = Field(description="One of: train / evaluate / paper / replay / walk_forward.")
    experiment_slug: str = Field(description="Slug of the registered RLExperimentSpec.")
    window: dict[str, Any] = Field(default_factory=dict)
    kill_switch_check: bool = True
    agent_spec_name: str = Field(default="strategy_executor")


class StrategyDispatchResponse(BaseModel):
    intent: str
    experiment_slug: str
    rationale: str = ""
    go: bool
    runtime_result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class QuantAgentSpec(BaseModel):
    name: str
    role: str | None = None
    description: str | None = None
    model: dict[str, Any] | None = None
    tools: list[str] = Field(default_factory=list)


class AlphaFormulaTemplate(BaseModel):
    """One curated symbolic alpha factor template.

    Mirrors the :class:`AlphaProposeResponse` shape so the gallery's
    "Use as template" deep-link can be re-used directly.
    """

    name: str
    formula: str
    rationale: str = ""
    expected_horizon_bars: int | None = None
    expected_direction: str | None = None
    tags: list[str] = Field(default_factory=list)


class BundledExample(BaseModel):
    """One bundled example surfaced in the Gallery's "Bundled" tab."""

    kind: str = Field(description="alpha_factor | rl_spec | agent_spec")
    name: str
    slug: str
    description: str | None = None
    source_path: str | None = Field(default=None, description="Relative repo path to the source file.")
    payload: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ExamplesLibraryResponse(BaseModel):
    items: list[BundledExample]


class AlphaFormulaTemplatesResponse(BaseModel):
    items: list[AlphaFormulaTemplate]


class LibraryHit(BaseModel):
    """One RAG-corpus library hit."""

    doc_id: str
    corpus: str
    score: float
    text: str
    meta: dict[str, Any] = Field(default_factory=dict)
    source_id: str | None = None
    vt_symbol: str | None = None
    as_of: str | None = None


class LibraryQueryResponse(BaseModel):
    corpus: str
    query: str | None
    items: list[LibraryHit]


_LIBRARY_CORPORA: tuple[str, ...] = (
    "alpha_factors",
    "backtest_summaries",
    "rl_trajectory_summaries",
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/factor/compile-preview", response_model=FactorCompilePreviewResponse)
def factor_compile_preview(req: FactorCompilePreviewRequest) -> FactorCompilePreviewResponse:
    """Test-compile a symbolic alpha formula through the AST sandbox.

    Useful for the frontend factor editor: the user types a formula
    and gets instant feedback on whether it compiles + which operators
    / fields it touches — without persisting anything to the DB or
    running a backtest.
    """
    from aqp.data.expressions_dsl import SymbolicAlphaError, compile_to_factor_node

    try:
        factor = compile_to_factor_node(req.formula, name=req.name)
    except SymbolicAlphaError as exc:
        return FactorCompilePreviewResponse(
            ok=False,
            formula=req.formula,
            name=req.name,
            error=str(exc),
        )
    return FactorCompilePreviewResponse(
        ok=True,
        formula=req.formula,
        name=factor.name,
        used_operators=sorted(factor.used_operators),
        used_fields=sorted(factor.used_fields),
    )


@router.post("/alpha-researcher/propose", response_model=AlphaProposeResponse)
def alpha_propose(req: AlphaProposeRequest) -> AlphaProposeResponse:
    """Drive the Alpha Researcher agent once and return its JSON proposal."""
    from aqp.agents.quant import AlphaResearcher

    researcher = AlphaResearcher(agent_spec_name=req.agent_spec_name)
    inputs: dict[str, Any] = {
        "intent": req.intent,
        "recent_factor_summary": list(req.recent_factor_summary or []),
    }
    if req.vt_symbol:
        inputs["vt_symbol"] = req.vt_symbol
    try:
        proposal = researcher.propose(inputs=inputs)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"AgentSpec {req.agent_spec_name!r} not registered: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("AlphaResearcher.propose failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return AlphaProposeResponse(
        name=str(proposal.get("name") or "anon"),
        formula=str(proposal.get("formula") or ""),
        rationale=str(proposal.get("rationale") or ""),
        expected_horizon_bars=proposal.get("expected_horizon_bars"),
        expected_direction=proposal.get("expected_direction"),
        raw_output=dict(proposal),
    )


@router.post("/alpha-researcher/evaluate", response_model=AlphaEvaluateResponse)
def alpha_evaluate(req: AlphaEvaluateRequest) -> AlphaEvaluateResponse:
    """Compile + backtest an alpha formula and return reward + metrics.

    Pulls bars via the default :class:`EventDrivenBacktester` substrate
    (which uses the DuckDB parquet history provider). For richer
    backtest configurations, drive the underlying :class:`RLRuntime`
    directly instead.
    """
    from aqp.agents.quant import AlphaResearcher

    researcher = AlphaResearcher()
    bars = _load_default_bars(req.vt_symbols)
    proposal = {
        "name": req.name,
        "formula": req.formula,
        "rationale": req.rationale,
    }
    try:
        result = researcher.evaluate(
            proposal,
            bars=bars,
            sharpe_weight=float(req.sharpe_weight),
            drawdown_weight=float(req.drawdown_weight),
            turnover_weight=float(req.turnover_weight),
        )
    except Exception as exc:
        logger.exception("AlphaResearcher.evaluate failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return AlphaEvaluateResponse(
        name=result.name,
        formula=result.formula,
        rationale=result.rationale,
        compiled=result.compiled,
        metrics=dict(result.metrics or {}),
        reward=float(result.reward),
        rejection_reason=result.rejection_reason,
    )


@router.post("/strategy-executor/dispatch", response_model=StrategyDispatchResponse)
def strategy_dispatch(req: StrategyDispatchRequest) -> StrategyDispatchResponse:
    """Drive the Strategy Executor agent + dispatch the resulting RL action.

    The agent decides whether to proceed (kill-switch check, duplicate
    detection) and emits a JSON action; the wrapper then dispatches
    the matching :class:`RLRuntime` call (train / evaluate / paper /
    replay / walk_forward).
    """
    from aqp.agents.quant import StrategyExecutor

    executor = StrategyExecutor(
        agent_spec_name=req.agent_spec_name,
        require_kill_switch_clear=bool(req.kill_switch_check),
    )
    inputs: dict[str, Any] = {
        "intent": req.intent,
        "experiment_slug": req.experiment_slug,
        "window": dict(req.window or {}),
        "kill_switch_check": bool(req.kill_switch_check),
    }
    try:
        outcome = executor.decide_and_run(inputs=inputs)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"AgentSpec {req.agent_spec_name!r} not registered: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("StrategyExecutor.decide_and_run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return StrategyDispatchResponse(
        intent=outcome.intent,
        experiment_slug=outcome.experiment_slug,
        rationale=outcome.rationale,
        go=bool(outcome.go),
        runtime_result=dict(outcome.runtime_result or {}),
        error=outcome.error,
    )


@router.get("/specs", response_model=list[QuantAgentSpec])
def list_quant_agent_specs() -> list[QuantAgentSpec]:
    """List the two registered quant-agent specs.

    Returns the metadata the UI panel needs (model, tool list, role
    label) without forcing the frontend to scrape the YAML directly.
    """
    out: list[QuantAgentSpec] = []
    for spec_name in ("alpha_researcher", "strategy_executor"):
        try:
            from aqp.agents.registry import get_agent_spec

            spec = get_agent_spec(spec_name)
        except Exception:
            continue
        out.append(
            QuantAgentSpec(
                name=getattr(spec, "name", spec_name),
                role=getattr(spec, "role", None),
                description=getattr(spec, "description", None),
                model=(
                    getattr(spec, "model", None).model_dump()
                    if getattr(spec, "model", None) is not None and hasattr(spec.model, "model_dump")
                    else None
                ),
                tools=[
                    getattr(t, "name", str(t)) if not isinstance(t, str) else t
                    for t in (getattr(spec, "tools", None) or [])
                ],
            )
        )
    return out


@router.get("/alpha-formula-templates", response_model=AlphaFormulaTemplatesResponse)
def list_alpha_formula_templates() -> AlphaFormulaTemplatesResponse:
    """Return the bundled symbolic alpha factor templates.

    Reads ``configs/strategies/alpha_factor_templates.yaml`` once and
    caches the parsed payload. Each entry mirrors the
    :class:`AlphaProposeResponse` shape so the Alpha Factor Studio's
    "Use as template" button can prefill the editor directly.
    """
    templates = _load_alpha_formula_templates()
    return AlphaFormulaTemplatesResponse(items=templates)


@router.get("/examples", response_model=ExamplesLibraryResponse)
def list_examples() -> ExamplesLibraryResponse:
    """Return the bundled examples library (alpha formulas + RL specs + agents).

    Drives the Gallery's "Bundled" tab. Three groups:
    1. ``alpha_factor`` — every entry in ``alpha_factor_templates.yaml``
    2. ``rl_spec`` — every YAML under ``configs/rl/policies/``
    3. ``agent_spec`` — the two quant-agent specs (alpha_researcher,
       strategy_executor)
    """
    items: list[BundledExample] = []

    for tpl in _load_alpha_formula_templates():
        items.append(
            BundledExample(
                kind="alpha_factor",
                name=tpl.name,
                slug=tpl.name,
                description=tpl.rationale.split("\n", 1)[0][:240] if tpl.rationale else None,
                source_path="configs/strategies/alpha_factor_templates.yaml",
                payload=tpl.model_dump(),
                tags=list(tpl.tags or []),
            )
        )

    for rl_payload, source_path in _load_rl_policy_specs():
        items.append(
            BundledExample(
                kind="rl_spec",
                name=str(rl_payload.get("name") or rl_payload.get("slug") or "rl-spec"),
                slug=str(rl_payload.get("slug") or rl_payload.get("name") or "rl-spec"),
                description=str(rl_payload.get("description") or "").strip().split("\n", 1)[0][:240]
                or None,
                source_path=source_path,
                payload=rl_payload,
                tags=list(rl_payload.get("annotations") or []),
            )
        )

    for agent_spec in list_quant_agent_specs():
        items.append(
            BundledExample(
                kind="agent_spec",
                name=agent_spec.name,
                slug=agent_spec.name,
                description=(agent_spec.description or "").strip().split("\n", 1)[0][:240] or None,
                source_path=f"configs/agents/{agent_spec.name}.yaml",
                payload=agent_spec.model_dump(),
                tags=[agent_spec.role] if agent_spec.role else [],
            )
        )
    return ExamplesLibraryResponse(items=items)


@router.get("/library/{corpus}", response_model=LibraryQueryResponse)
def library_query(
    corpus: str,
    q: str = "",
    k: int = 12,
    level: str = "l0",
) -> LibraryQueryResponse:
    """Semantic-search one of the alpha-base RAG corpora.

    Allowed corpora are the three Phase 7 alpha-base corpora:
    ``alpha_factors`` / ``backtest_summaries`` / ``rl_trajectory_summaries``.
    Other corpus names return 404 (rule 11 keeps the RAG surface narrow).
    Empty ``q`` triggers a "recent" fall-back that returns the most
    recently indexed entries (best-effort).
    """
    if corpus not in _LIBRARY_CORPORA:
        raise HTTPException(
            status_code=404,
            detail=f"unknown library corpus {corpus!r}; allowed: {list(_LIBRARY_CORPORA)}",
        )
    try:
        from aqp.rag.hierarchy import get_default_rag
    except Exception:
        logger.exception("RAG library: failed to acquire HierarchicalRAG")
        return LibraryQueryResponse(corpus=corpus, query=q or None, items=[])
    rag = get_default_rag()
    query_text = q.strip() or _DEFAULT_LIBRARY_QUERIES.get(corpus, "summary")
    try:
        hits = rag.query(query_text, corpus=corpus, level=level, k=int(k))
    except Exception:
        logger.exception("RAG library: query(%s) failed", corpus)
        return LibraryQueryResponse(corpus=corpus, query=q or None, items=[])

    items: list[LibraryHit] = []
    for hit in hits or []:
        meta_dict = dict(getattr(hit, "meta", {}) or {})
        items.append(
            LibraryHit(
                doc_id=str(getattr(hit, "doc_id", "")),
                corpus=str(getattr(hit, "corpus", corpus)),
                score=float(getattr(hit, "score", 0.0) or 0.0),
                text=str(getattr(hit, "text", ""))[:2000],
                meta=meta_dict,
                source_id=str(getattr(hit, "source_id", "") or "") or None,
                vt_symbol=str(getattr(hit, "vt_symbol", "") or "") or None,
                as_of=str(getattr(hit, "as_of", "") or "") or None,
            )
        )
    return LibraryQueryResponse(corpus=corpus, query=q or None, items=items)


_QUANT_SPEC_NAMES: tuple[str, ...] = ("alpha_researcher", "strategy_executor")


@router.post("/halt", status_code=200)
def halt_quant_agents() -> dict[str, Any]:
    """Halt only the two quant agents (AlphaResearcher + StrategyExecutor).

    A narrow companion to the global ``/agents/halt`` endpoint —
    surfaces in the kill-switch fan-out and gives users a way to
    stop only LLM-driven factor mining + strategy dispatch while
    leaving other ``AgentRuntime`` cohorts (Research / Selection /
    Trader) alone.

    Idempotent: returns 200 even if nothing was running. Mirrors the
    ``/agents/halt`` pattern (revoke the Celery task, flip
    ``AgentRunV2.status="halted"``).
    """
    try:
        from sqlalchemy import select

        from aqp.persistence.models_agents import AgentRunV2
        from aqp.persistence.session import get_session
        from aqp.tasks.celery_app import celery_app as _celery
    except Exception:
        logger.exception("quant-agents halt: imports failed")
        return {"ok": False, "stopped": 0, "task_ids": [], "failures": ["imports failed"]}

    revoked: list[str] = []
    failures: list[dict[str, str]] = []
    try:
        with get_session() as session:
            rows = (
                session.execute(
                    select(AgentRunV2).where(
                        AgentRunV2.status.in_(["running", "pending"]),
                        AgentRunV2.spec_name.in_(_QUANT_SPEC_NAMES),
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                tid = (row.task_id or "").strip()
                if tid:
                    try:
                        _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
                        revoked.append(tid)
                    except Exception as exc:
                        failures.append({"task_id": tid, "error": str(exc)})
                row.status = "halted"
                row.error = (row.error or "") + "\nhalted by quant-agents kill switch"
    except Exception as exc:
        logger.exception("quant-agents halt: db pass failed")
        failures.append({"step": "db_pass", "error": str(exc)})

    return {
        "ok": not failures,
        "stopped": len(revoked),
        "task_ids": revoked,
        "failures": failures,
        "specs": list(_QUANT_SPEC_NAMES),
    }


# ---------------------------------------------------------------------------
# Realtime presence (OOS extension)
# ---------------------------------------------------------------------------


class _PresenceRoom:
    """In-process presence room for the Alpha Factor Studio.

    Each connected client gets a stable participant id (server-assigned
    UUID, never trusted from the client). The room broadcasts the
    full participant roster on every join / leave / heartbeat so the
    client just renders ``state.participants`` directly.

    Single-process only — sufficient for the dev cluster (uvicorn 1
    worker). A horizontal-scale upgrade would route through Redis
    pub/sub or the existing ``aqp.ws.broker`` helper.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._participants: dict[str, dict[str, Any]] = {}
        self._sockets: dict[str, WebSocket] = {}

    async def join(
        self,
        participant_id: str,
        ws: WebSocket,
        display_name: str,
    ) -> None:
        async with self._lock:
            self._sockets[participant_id] = ws
            self._participants[participant_id] = {
                "participant_id": participant_id,
                "display_name": display_name,
                "joined_at": time.time(),
                "last_seen": time.time(),
            }

    async def leave(self, participant_id: str) -> None:
        async with self._lock:
            self._sockets.pop(participant_id, None)
            self._participants.pop(participant_id, None)

    async def touch(self, participant_id: str) -> None:
        async with self._lock:
            row = self._participants.get(participant_id)
            if row is not None:
                row["last_seen"] = time.time()

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "stage": "presence",
                "participants": list(self._participants.values()),
                "count": len(self._participants),
            }

    async def broadcast(self) -> None:
        snap = await self.snapshot()
        # Iterate over a copy because send_json may surface a
        # disconnect that mutates _sockets.
        async with self._lock:
            targets = list(self._sockets.items())
        for pid, sock in targets:
            try:
                await sock.send_json(snap)
            except Exception:
                # Best-effort cleanup; the disconnect handler will
                # also fire below.
                await self.leave(pid)


_ALPHA_PRESENCE = _PresenceRoom()
_HEARTBEAT_INTERVAL_S = 15.0


@router.websocket("/alpha-factors/presence")
async def alpha_factor_presence(ws: WebSocket) -> None:
    """Real-time presence WS for the Alpha Factor Studio.

    The Studio opens a single subscription per session and gets a
    push of the participant list on every join / leave / heartbeat.
    No CRDT / co-authoring — just "X others are also editing alphas
    right now" with display names.

    Query params:
      - ``display_name`` (optional) — short label rendered on the
        peer's badge. Defaults to ``Anonymous``.
    """
    await ws.accept()
    display_name = ws.query_params.get("display_name") or "Anonymous"
    participant_id = uuid.uuid4().hex[:8]
    await _ALPHA_PRESENCE.join(participant_id, ws, display_name)
    await _ALPHA_PRESENCE.broadcast()
    try:
        await ws.send_json({
            "stage": "welcome",
            "participant_id": participant_id,
        })
        # Read loop: clients may send ``{"stage":"heartbeat"}`` or
        # ``{"stage":"update","display_name":"..."}`` to refresh
        # their roster row.
        while True:
            try:
                msg = await asyncio.wait_for(
                    ws.receive_json(), timeout=_HEARTBEAT_INTERVAL_S * 2
                )
            except asyncio.TimeoutError:
                # Client went idle — keep the row alive ourselves so
                # the badge doesn't flicker.
                await _ALPHA_PRESENCE.touch(participant_id)
                continue
            stage = (msg or {}).get("stage") if isinstance(msg, dict) else None
            if stage == "update":
                new_name = (msg.get("display_name") or display_name).strip()
                if new_name:
                    display_name = new_name
                    await _ALPHA_PRESENCE.join(participant_id, ws, display_name)
                    await _ALPHA_PRESENCE.broadcast()
                continue
            await _ALPHA_PRESENCE.touch(participant_id)
    except WebSocketDisconnect:
        logger.debug("alpha-factor presence disconnected: %s", participant_id)
    except Exception:
        logger.exception("alpha-factor presence error: %s", participant_id)
    finally:
        await _ALPHA_PRESENCE.leave(participant_id)
        await _ALPHA_PRESENCE.broadcast()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Default fallback queries when the user passes an empty `q`. We use a
# broad descriptive sentence so the embedder still returns top-scored
# entries rather than zeros (semantic search does not gracefully handle
# empty input across embedding models).
_DEFAULT_LIBRARY_QUERIES: dict[str, str] = {
    "alpha_factors": "alpha factor formula symbolic rationale",
    "backtest_summaries": "backtest performance sharpe drawdown turnover",
    "rl_trajectory_summaries": "reinforcement learning run summary equity",
}


_TEMPLATE_CACHE: list[AlphaFormulaTemplate] | None = None


def _load_alpha_formula_templates() -> list[AlphaFormulaTemplate]:
    """Read + cache the bundled alpha formula templates from disk."""
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return list(_TEMPLATE_CACHE)
    try:
        import yaml
        from pathlib import Path

        candidates = [
            Path("/app/configs/strategies/alpha_factor_templates.yaml"),
            Path("configs/strategies/alpha_factor_templates.yaml"),
        ]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            logger.warning(
                "alpha_factor_templates.yaml not found; returning empty template set"
            )
            _TEMPLATE_CACHE = []
            return []
        with open(path, encoding="utf-8") as fh:
            payload = yaml.safe_load(fh) or {}
        raw_items = payload.get("templates") or []
        out: list[AlphaFormulaTemplate] = []
        for raw in raw_items:
            try:
                out.append(AlphaFormulaTemplate(**raw))
            except Exception:
                logger.warning("Skipping malformed alpha template: %r", raw)
        _TEMPLATE_CACHE = out
        return list(out)
    except Exception:
        logger.exception("Failed to load alpha_factor_templates.yaml")
        _TEMPLATE_CACHE = []
        return []


_RL_SPEC_CACHE: list[tuple[dict[str, Any], str]] | None = None


def _load_rl_policy_specs() -> list[tuple[dict[str, Any], str]]:
    """Read + cache the bundled RL policy specs from ``configs/rl/policies/``."""
    global _RL_SPEC_CACHE
    if _RL_SPEC_CACHE is not None:
        return list(_RL_SPEC_CACHE)
    try:
        import yaml
        from pathlib import Path

        roots = [
            Path("/app/configs/rl/policies"),
            Path("configs/rl/policies"),
        ]
        root = next((r for r in roots if r.exists()), None)
        if root is None:
            logger.warning("configs/rl/policies not found; returning empty RL spec set")
            _RL_SPEC_CACHE = []
            return []
        out: list[tuple[dict[str, Any], str]] = []
        for yaml_path in sorted(root.glob("*.yaml")):
            try:
                with open(yaml_path, encoding="utf-8") as fh:
                    payload = yaml.safe_load(fh) or {}
                rel = str(yaml_path).replace("\\", "/")
                out.append((payload, rel))
            except Exception:
                logger.warning("Skipping malformed RL spec: %s", yaml_path)
        _RL_SPEC_CACHE = out
        return list(out)
    except Exception:
        logger.exception("Failed to load RL policy specs")
        _RL_SPEC_CACHE = []
        return []


def _load_default_bars(vt_symbols: list[str] | None) -> Any:
    """Load OHLCV bars for the requested universe via DuckDB parquet.

    Returns a long-format DataFrame ready for the
    :class:`EventDrivenBacktester` substrate. Falls back to an empty
    frame so the AlphaResearcher.evaluate path still returns a
    structured result with empty metrics.
    """
    try:
        import pandas as pd
        from pathlib import Path

        from aqp.config import settings
        from aqp.core.types import Symbol
        from aqp.data.duckdb_engine import DuckDBHistoryProvider
    except Exception:
        logger.exception("Bars loader: imports failed; returning empty frame")
        try:
            import pandas as pd

            return pd.DataFrame()
        except Exception:
            return None
    if not vt_symbols:
        return pd.DataFrame()
    try:
        provider = DuckDBHistoryProvider(Path(settings.parquet_dir))
        sym_objs = [Symbol.parse(s) for s in vt_symbols]
        end = pd.Timestamp.utcnow().tz_localize(None)
        start = end - pd.Timedelta(days=365 * 3)
        bars = provider.get_bars(sym_objs, start, end)
        if bars is None or bars.empty:
            return pd.DataFrame()
        return bars
    except Exception:
        logger.exception("Bars loader: DuckDB query failed; returning empty frame")
        return pd.DataFrame()


__all__ = ["router"]
