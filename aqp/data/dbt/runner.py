"""Programmatic dbt command runner with lazy optional imports."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aqp.data.dbt.artifacts import artifact_paths, load_manifest_models, load_run_results
from aqp.data.dbt.project import DbtProjectManager

logger = logging.getLogger(__name__)


@dataclass
class DbtCommandResult:
    """Serializable outcome for one dbt invocation."""

    command: str
    args: list[str]
    success: bool
    exception: str | None = None
    result_type: str | None = None
    models: list[dict[str, Any]] = field(default_factory=list)
    run_results: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "args": list(self.args),
            "success": self.success,
            "exception": self.exception,
            "result_type": self.result_type,
            "models": list(self.models),
            "run_results": dict(self.run_results),
            "artifacts": dict(self.artifacts),
        }


class DbtRunnerService:
    """Small wrapper around ``dbtRunner`` using explicit project/profile paths."""

    def __init__(self, manager: DbtProjectManager | None = None) -> None:
        self.manager = manager or DbtProjectManager.from_settings()

    def parse(self) -> DbtCommandResult:
        return self.invoke("parse")

    def list(self, *, select: list[str] | None = None, output: str = "json") -> DbtCommandResult:
        return self.invoke("list", select=select, extra_args=["--output", output])

    def compile(self, *, select: list[str] | None = None) -> DbtCommandResult:
        return self.invoke("compile", select=select)

    def build(self, *, select: list[str] | None = None) -> DbtCommandResult:
        return self.invoke("build", select=select)

    def test(self, *, select: list[str] | None = None) -> DbtCommandResult:
        return self.invoke("test", select=select)

    def show(
        self,
        *,
        select: list[str] | None = None,
        inline: str | None = None,
        limit: int = 50,
    ) -> DbtCommandResult:
        extra_args = ["--limit", str(limit)]
        if inline:
            extra_args.extend(["--inline", inline])
        return self.invoke("show", select=select, extra_args=extra_args)

    def invoke(
        self,
        command: str,
        *,
        select: list[str] | None = None,
        extra_args: list[str] | None = None,
    ) -> DbtCommandResult:
        """Invoke dbt, returning artifact summaries even when dbt fails."""
        self.manager.ensure_project()
        args = self._base_args(command)
        selectors = [s for s in (select or []) if str(s).strip()]
        if selectors:
            args.extend(["--select", *selectors])
        args.extend(extra_args or [])

        try:
            from dbt.cli.main import dbtRunner  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return DbtCommandResult(
                command=command,
                args=args,
                success=False,
                exception=(
                    "dbt is not installed. Install the optional extra with "
                    "`pip install 'agentic-quant-platform[dbt]'`."
                ),
                artifacts=artifact_paths(self.manager.project_dir),
                result_type=type(exc).__name__,
            )

        try:
            runner = dbtRunner()
            result = runner.invoke(args)
        except Exception as exc:  # noqa: BLE001
            logger.exception("dbt %s failed before result construction", command)
            return DbtCommandResult(
                command=command,
                args=args,
                success=False,
                exception=str(exc),
                artifacts=artifact_paths(self.manager.project_dir),
                models=load_manifest_models(self.manager.project_dir),
                run_results=load_run_results(self.manager.project_dir),
                result_type=type(exc).__name__,
            )

        exception = getattr(result, "exception", None)
        typed_result = getattr(result, "result", None)
        outcome = DbtCommandResult(
            command=command,
            args=args,
            success=bool(getattr(result, "success", False)),
            exception=str(exception) if exception else None,
            result_type=type(typed_result).__name__ if typed_result is not None else None,
            artifacts=artifact_paths(self.manager.project_dir),
            models=load_manifest_models(self.manager.project_dir),
            run_results=load_run_results(self.manager.project_dir),
        )
        _emit_dbt_lineage(outcome)
        return outcome

    def _base_args(self, command: str) -> list[str]:
        return [
            command,
            "--project-dir",
            str(self.manager.project_dir),
            "--profiles-dir",
            str(self.manager.profiles_dir),
            "--target",
            self.manager.target,
            "--quiet",
        ]


def default_runner() -> DbtRunnerService:
    """Factory used by routes and engine nodes."""
    return DbtRunnerService(DbtProjectManager.from_settings())


def _emit_dbt_lineage(outcome: DbtCommandResult) -> None:
    """Fire one ``dbt`` lineage event per built model.

    Best-effort. Reads the ``models`` artefact rather than the raw run
    results so we can capture the model's relation name (which becomes
    the lineage ``target_table_id``).
    """
    try:
        from aqp.data.catalog.lineage import LineageEvent, get_lineage_bus

        if outcome.command not in {"build", "run", "compile", "test"}:
            return
        bus = get_lineage_bus()
        if not outcome.models:
            bus.emit(
                LineageEvent(
                    transform_kind="dbt",
                    target_table_id=None,
                    actor=f"dbt.{outcome.command}",
                    actor_kind="service",
                    service_name="dbt",
                    summary=(
                        f"dbt {outcome.command} success={outcome.success} "
                        f"(no models)"
                    ),
                    details={
                        "command": outcome.command,
                        "success": outcome.success,
                        "exception": outcome.exception,
                    },
                )
            )
            return
        for model in outcome.models:
            target = (
                model.get("relation_name")
                or model.get("alias")
                or model.get("name")
            )
            bus.emit(
                LineageEvent(
                    transform_kind="dbt",
                    target_table_id=str(target) if target else None,
                    actor=f"dbt.{outcome.command}",
                    actor_kind="service",
                    service_name="dbt",
                    summary=(
                        f"dbt {outcome.command} model={model.get('name')} "
                        f"success={outcome.success}"
                    ),
                    details={
                        "command": outcome.command,
                        "success": outcome.success,
                        "package_name": model.get("package_name"),
                        "schema": model.get("schema"),
                        "depends_on": model.get("depends_on"),
                    },
                )
            )
    except Exception:  # noqa: BLE001
        logger.debug("dbt lineage emit failed", exc_info=True)

