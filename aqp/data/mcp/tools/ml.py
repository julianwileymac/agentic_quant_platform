"""``data.ml.*`` MCP tools — agent-facing MLOps catalog.

This module fulfils Hard Rule 22 for the MLOps subsystem: every agent
read against ``ModelVersion`` / ``ModelDeployment`` / ``MlSkill`` rows
+ every agent invocation of an MLOps handler (cache / load / save /
store / productionize / serve) flows through one of the tools below.

Tools:

- ``data.ml.models.list`` — list ``ModelVersion`` rows.
- ``data.ml.models.describe`` — describe one model.
- ``data.ml.deployments.list`` — list ``ModelDeployment`` rows.
- ``data.ml.predict`` / ``data.ml.forecast`` / ``data.ml.classify`` /
  ``data.ml.segment`` / ``data.ml.analyze`` — synchronous inference
  via the matching :mod:`aqp_models.interfaces` wrapper.
- ``data.ml.models.pull_huggingface`` / ``data.ml.models.pull_torchhub``
  — pull a snapshot via the matching :mod:`aqp_models.adapters`.
- ``data.ml.skills.list`` / ``data.ml.skills.run`` — list registered
  MLSkills + execute one through :class:`MLSkillRuntime`.
- ``data.ml.compile`` — drive :class:`ProductionizeHandler`.
- ``data.ml.serving.list`` — descriptors for every active
  :class:`ServingSession`.

Every tool subclasses :class:`DataMCPTool` so the existing in-process
bridge + FastAPI router + ``aqp-data-mcp`` stdio binary all surface
the catalog uniformly.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


def _handler_ctx(ctx: MCPToolContext) -> Any:
    """Bridge an :class:`MCPToolContext` into an :class:`HandlerContext`."""
    from aqp_models.handlers.base import HandlerContext

    return HandlerContext(
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        session_id=ctx.session_id,
        workspace_id=ctx.workspace_id,
        project_id=ctx.project_id,
        granted_scopes=tuple(ctx.granted_scopes),
        request_id=ctx.request_id,
    )


# ---------------------------------------------------------------------------
# data.ml.models.list
# ---------------------------------------------------------------------------


class _ListModelsArgs(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    registry_name: str | None = None


@register_data_mcp_tool
class ListModelsTool(DataMCPTool):
    name = "data.ml.models.list"
    description = (
        "List registered ML ModelVersion rows (alpha / forecast / classifier"
        " models). Filter by registry_name to narrow the result."
    )
    args_schema = _ListModelsArgs
    category = "ml"
    tags = ("ml",)

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models import ModelVersion

        limit = int(arguments.get("limit") or 50)
        registry_name = arguments.get("registry_name")
        with get_session() as session:
            stmt = select(ModelVersion).order_by(desc(ModelVersion.created_at)).limit(limit)
            if registry_name:
                stmt = stmt.where(ModelVersion.registry_name == registry_name)
            rows = session.execute(stmt).scalars().all()
            data = [_summarise_model(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data={"models": data, "n_models": len(data)},
            summary=f"{len(data)} models",
            rows_returned=len(data),
        )


# ---------------------------------------------------------------------------
# data.ml.models.describe
# ---------------------------------------------------------------------------


class _DescribeModelArgs(BaseModel):
    model_version_id: str


@register_data_mcp_tool
class DescribeModelTool(DataMCPTool):
    name = "data.ml.models.describe"
    description = "Describe one ModelVersion row by id, including metrics."
    args_schema = _DescribeModelArgs
    category = "ml"
    tags = ("ml",)

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models import ModelVersion

        model_version_id = arguments["model_version_id"]
        with get_session() as session:
            row = session.get(ModelVersion, model_version_id)
            if row is None:
                return MCPToolResult(ok=False, error=f"model_version {model_version_id!r} not found")
            return MCPToolResult(
                ok=True,
                data=_summarise_model(row),
                summary=row.registry_name,
            )


# ---------------------------------------------------------------------------
# data.ml.deployments.list
# ---------------------------------------------------------------------------


class _ListDeploymentsArgs(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    status: str | None = None


@register_data_mcp_tool
class ListDeploymentsTool(DataMCPTool):
    name = "data.ml.deployments.list"
    description = "List ModelDeployment rows; filter by ``status``."
    args_schema = _ListDeploymentsArgs
    category = "ml"
    tags = ("ml",)

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models import ModelDeployment

        with get_session() as session:
            stmt = (
                select(ModelDeployment)
                .order_by(desc(ModelDeployment.created_at))
                .limit(int(arguments.get("limit") or 50))
            )
            status = arguments.get("status")
            if status:
                stmt = stmt.where(ModelDeployment.status == status)
            rows = session.execute(stmt).scalars().all()
            data = [_summarise_deployment(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data={"deployments": data, "n_deployments": len(data)},
            rows_returned=len(data),
        )


# ---------------------------------------------------------------------------
# data.ml.predict / forecast / classify / segment / analyze
# ---------------------------------------------------------------------------


class _PredictArgs(BaseModel):
    model_alias: str = Field(
        ..., description="Registered model alias (e.g. 'XGBModel')."
    )
    features: dict[str, Any] | list[list[float]] | list[float]
    model_kwargs: dict[str, Any] = Field(default_factory=dict)


@register_data_mcp_tool
class PredictTool(DataMCPTool):
    name = "data.ml.predict"
    description = (
        "Run a Predictor against an arbitrary feature row/matrix. The"
        " model is resolved through aqp.core.registry then wrapped in"
        " the agent-facing Predictor interface."
    )
    args_schema = _PredictArgs
    category = "ml"
    tags = ("ml", "inference")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        return _run_interface_inference(
            kind="predictor",
            method="predict",
            arguments=arguments,
            ctx=ctx,
            payload_key="features",
        )


class _ForecastArgs(BaseModel):
    model_alias: str
    history: list[list[float]] | list[float]
    horizon: int = Field(..., ge=1, le=500)
    model_kwargs: dict[str, Any] = Field(default_factory=dict)


@register_data_mcp_tool
class ForecastTool(DataMCPTool):
    name = "data.ml.forecast"
    description = "Run a multi-step Forecaster over a history series."
    args_schema = _ForecastArgs
    category = "ml"
    tags = ("ml", "forecast")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        return _run_interface_inference(
            kind="forecaster",
            method="forecast",
            arguments=arguments,
            ctx=ctx,
            payload_key="history",
        )


class _ClassifyArgs(BaseModel):
    model_alias: str
    features: dict[str, Any] | list[list[float]] | list[float]
    classes: list[str] | None = None
    model_kwargs: dict[str, Any] = Field(default_factory=dict)


@register_data_mcp_tool
class ClassifyTool(DataMCPTool):
    name = "data.ml.classify"
    description = "Classify a feature row using a Classifier interface."
    args_schema = _ClassifyArgs
    category = "ml"
    tags = ("ml", "classify")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        return _run_interface_inference(
            kind="classifier",
            method="classify",
            arguments=arguments,
            ctx=ctx,
            payload_key="features",
            extra_kwargs={"classes": arguments.get("classes")},
        )


class _SegmentArgs(BaseModel):
    model_alias: str
    series: list[float]
    window: int = Field(default=30, ge=2, le=2000)
    threshold: float = Field(default=3.0)
    model_kwargs: dict[str, Any] = Field(default_factory=dict)


@register_data_mcp_tool
class SegmentTool(DataMCPTool):
    name = "data.ml.segment"
    description = "Detect structural breaks in a 1D series."
    args_schema = _SegmentArgs
    category = "ml"
    tags = ("ml", "regime")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp.core.registry import build_from_config
        from aqp_models.interfaces import Segmenter

        cfg = {
            "class": arguments["model_alias"],
            "kwargs": dict(arguments.get("model_kwargs") or {}),
        }
        try:
            model = build_from_config(cfg)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"resolve {arguments['model_alias']!r} failed: {exc}")

        wrapper = Segmenter(
            model=model,
            alias=arguments["model_alias"],
            window=int(arguments.get("window", 30)),
            threshold=float(arguments.get("threshold", 3.0)),
        )
        try:
            boundaries, metadata = wrapper.segment(arguments.get("series") or [])
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=str(exc))
        return MCPToolResult(
            ok=True,
            data={
                "boundaries": [b.to_json() for b in boundaries],
                "metadata": metadata.to_json(),
            },
            summary=f"{len(boundaries)} breaks",
            rows_returned=len(boundaries),
        )


class _AnalyzeArgs(BaseModel):
    model_alias: str
    text: str | list[str] | None = None
    text_column: str = "text"
    model_kwargs: dict[str, Any] = Field(default_factory=dict)


@register_data_mcp_tool
class AnalyzeTool(DataMCPTool):
    name = "data.ml.analyze"
    description = (
        "Analyse unstructured text (single doc or list) via an Analyzer"
        " interface — sentiment / event extraction / entity tagging."
    )
    args_schema = _AnalyzeArgs
    category = "ml"
    tags = ("ml", "nlp")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp.core.registry import build_from_config
        from aqp_models.interfaces import Analyzer

        cfg = {
            "class": arguments["model_alias"],
            "kwargs": dict(arguments.get("model_kwargs") or {}),
        }
        try:
            model = build_from_config(cfg)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"resolve {arguments['model_alias']!r} failed: {exc}")

        wrapper = Analyzer(
            model=model,
            alias=arguments["model_alias"],
            text_column=str(arguments.get("text_column", "text")),
        )
        try:
            result = wrapper.analyze(arguments.get("text"))
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=str(exc))
        return MCPToolResult(ok=True, data=result.to_json(), summary="analyzed")


# ---------------------------------------------------------------------------
# data.ml.models.pull_huggingface / pull_torchhub
# ---------------------------------------------------------------------------


class _PullArgs(BaseModel):
    model_name: str = Field(..., description="Repo id, e.g. 'ProsusAI/finbert'")
    revision: str | None = None
    include_examples: bool = False


@register_data_mcp_tool
class PullHuggingFaceTool(DataMCPTool):
    name = "data.ml.models.pull_huggingface"
    description = (
        "Pull a HuggingFace Hub snapshot via the HuggingFaceAdapter."
        " Resolves the HF token through CredentialResolver — no raw"
        " environment reads."
    )
    args_schema = _PullArgs
    mutates = True
    required_scopes = ("data:write",)
    category = "ml"
    tags = ("ml", "pull")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp_models.adapters import get_adapter

        adapter = get_adapter("huggingface")
        result = adapter.pull(
            arguments["model_name"],
            revision=arguments.get("revision"),
            include_examples=bool(arguments.get("include_examples", False)),
        )
        return MCPToolResult(
            ok=bool(result.ok),
            data=result.to_json(),
            error=result.error,
            summary=f"hf:{arguments['model_name']}",
        )


@register_data_mcp_tool
class PullTorchHubTool(DataMCPTool):
    name = "data.ml.models.pull_torchhub"
    description = (
        "Pull a TorchHub model via the TorchHubAdapter. The model name"
        " MUST be in the platform allow-list (DEFAULT_ALLOWLIST + the"
        " entries supplied via CredentialResolver)."
    )
    args_schema = _PullArgs
    mutates = True
    required_scopes = ("data:write",)
    category = "ml"
    tags = ("ml", "pull")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp_models.adapters import get_adapter

        adapter = get_adapter("torchhub")
        result = adapter.pull(
            arguments["model_name"],
            revision=arguments.get("revision"),
            include_examples=bool(arguments.get("include_examples", False)),
        )
        return MCPToolResult(
            ok=bool(result.ok),
            data=result.to_json(),
            error=result.error,
            summary=f"torchhub:{arguments['model_name']}",
        )


# ---------------------------------------------------------------------------
# data.ml.skills.list / run
# ---------------------------------------------------------------------------


@register_data_mcp_tool
class ListSkillsTool(DataMCPTool):
    name = "data.ml.skills.list"
    description = "List every MLSkill registered in the in-memory + YAML registry."
    category = "ml"
    tags = ("ml", "skill")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp_models.registry import list_skill_specs

        specs = list_skill_specs()
        data = [
            {
                "name": s.name,
                "kind": s.kind,
                "description": s.description,
                "annotations": list(s.annotations),
                "n_steps": len(s.steps),
                "spec_hash": s.spec_hash(),
            }
            for s in specs
        ]
        return MCPToolResult(
            ok=True,
            data={"skills": data, "n_skills": len(data)},
            summary=f"{len(data)} skills",
            rows_returned=len(data),
        )


class _RunSkillArgs(BaseModel):
    name: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    experiment_id: str | None = None
    test_id: str | None = None


@register_data_mcp_tool
class RunSkillTool(DataMCPTool):
    name = "data.ml.skills.run"
    description = (
        "Execute a registered MLSkill via MLSkillRuntime. Snapshots the"
        " spec hash, writes a ml_skill_runs row, and emits a lineage"
        " event."
    )
    args_schema = _RunSkillArgs
    mutates = True
    required_scopes = ("data:write",)
    category = "ml"
    tags = ("ml", "skill")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp_models.registry import get_skill_spec
        from aqp_models.runtime import MLSkillRuntime

        try:
            spec = get_skill_spec(arguments["name"])
        except KeyError as exc:
            return MCPToolResult(ok=False, error=str(exc))

        runtime = MLSkillRuntime(spec)
        result = runtime.run(
            inputs=dict(arguments.get("inputs") or {}),
            ctx=_handler_ctx(ctx),
            experiment_id=arguments.get("experiment_id"),
            test_id=arguments.get("test_id"),
        )
        return MCPToolResult(
            ok=(result.status == "succeeded"),
            data=result.to_json(),
            error=result.error,
            summary=f"skill {arguments['name']} {result.status}",
        )


# ---------------------------------------------------------------------------
# data.ml.compile
# ---------------------------------------------------------------------------


class _CompileArgs(BaseModel):
    model_alias: str
    target: str = Field(..., description="onnx | tensorrt | torchscript | quantize")
    compile_kwargs: dict[str, Any] = Field(default_factory=dict)
    model_kwargs: dict[str, Any] = Field(default_factory=dict)
    output_path: str | None = None


@register_data_mcp_tool
class CompileArtifactTool(DataMCPTool):
    name = "data.ml.compile"
    description = (
        "Compile a model to ONNX / TensorRT / TorchScript via the"
        " ProductionizeHandler. Returns the artifact path + SHA-256."
    )
    args_schema = _CompileArgs
    mutates = True
    required_scopes = ("data:write",)
    category = "ml"
    tags = ("ml", "productionize")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp.core.registry import build_from_config
        from aqp_models.handlers import ProductionizeHandler

        cfg = {
            "class": arguments["model_alias"],
            "kwargs": dict(arguments.get("model_kwargs") or {}),
        }
        try:
            model = build_from_config(cfg)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=str(exc))

        handler = ProductionizeHandler()
        result = handler.invoke(
            ctx=_handler_ctx(ctx),
            model=model,
            target=arguments["target"],
            compiler_kwargs=dict(arguments.get("compile_kwargs") or {}),
            output_path=arguments.get("output_path"),
        )
        return MCPToolResult(
            ok=bool(result.ok),
            data=result.data,
            error=result.error,
            summary=result.summary,
            metadata=dict(result.metadata),
            elapsed_ms=result.elapsed_ms,
        )


# ---------------------------------------------------------------------------
# data.ml.serving.list
# ---------------------------------------------------------------------------


@register_data_mcp_tool
class ListServingSessionsTool(DataMCPTool):
    name = "data.ml.serving.list"
    description = "Descriptors for every active continuous-batching session."
    category = "ml"
    tags = ("ml", "serving")

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp_models.handlers import ServeHandler

        descriptors = ServeHandler.list_sessions()
        return MCPToolResult(
            ok=True,
            data={"sessions": descriptors, "n_sessions": len(descriptors)},
            summary=f"{len(descriptors)} active sessions",
            rows_returned=len(descriptors),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarise_model(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "registry_name": row.registry_name,
        "algo": row.algo,
        "stage": row.stage,
        "mlflow_version": row.mlflow_version,
        "dataset_hash": row.dataset_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "metrics": dict(row.metrics or {}),
    }


def _summarise_deployment(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "model_version_id": row.model_version_id,
        "alpha_class": row.alpha_class,
        "long_threshold": row.long_threshold,
        "short_threshold": row.short_threshold,
        "allow_short": row.allow_short,
        "top_k": row.top_k,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _run_interface_inference(
    *,
    kind: str,
    method: str,
    arguments: dict[str, Any],
    ctx: MCPToolContext,
    payload_key: str,
    extra_kwargs: dict[str, Any] | None = None,
) -> MCPToolResult:
    """Shared body for predict / forecast / classify."""
    from aqp.core.registry import build_from_config
    from aqp_models.interfaces import wrap_model

    cfg = {
        "class": arguments["model_alias"],
        "kwargs": dict(arguments.get("model_kwargs") or {}),
    }
    try:
        model = build_from_config(cfg)
    except Exception as exc:  # noqa: BLE001
        return MCPToolResult(ok=False, error=f"resolve {arguments['model_alias']!r} failed: {exc}")

    wrap_kwargs = {k: v for k, v in (extra_kwargs or {}).items() if v is not None}
    try:
        wrapper = wrap_model(model, kind=kind, alias=arguments["model_alias"], **wrap_kwargs)
    except (KeyError, TypeError) as exc:
        return MCPToolResult(ok=False, error=f"wrap as {kind!r} failed: {exc}")

    payload = arguments.get(payload_key)
    try:
        if kind == "forecaster":
            result = wrapper.forecast(payload or [], horizon=int(arguments.get("horizon", 1)))
        else:
            result = getattr(wrapper, method)(payload)
    except Exception as exc:  # noqa: BLE001
        return MCPToolResult(ok=False, error=f"{method} failed: {exc}")

    return MCPToolResult(
        ok=True,
        data=result.to_json(),
        summary=f"{kind}:{arguments['model_alias']}",
    )


__all__ = [
    "AnalyzeTool",
    "ClassifyTool",
    "CompileArtifactTool",
    "DescribeModelTool",
    "ForecastTool",
    "ListDeploymentsTool",
    "ListModelsTool",
    "ListServingSessionsTool",
    "ListSkillsTool",
    "PredictTool",
    "PullHuggingFaceTool",
    "PullTorchHubTool",
    "RunSkillTool",
    "SegmentTool",
]
