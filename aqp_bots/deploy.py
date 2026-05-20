"""Deployment dispatcher for bots.

Two backends ship in tree:

- :class:`PaperSessionTarget` — wraps the existing
  :class:`aqp.trading.session.PaperTradingSession`. Phase 1 deliverable:
  the simplest "deploy" that produces a running bot.
- :class:`BacktestOnlyTarget` — convenience target that runs a single
  backtest and persists the result onto the deployment row. Used by
  CI / smoke jobs that want a deploy artefact without a long-running
  process.
- :class:`KubernetesTarget` — Phase 5: render a Kubernetes manifest
  (Deployment + ConfigMap; optional Argo ``WorkflowTemplate``) into
  ``deploy/k8s/bots/<slug>.yaml`` and (optionally) apply it. Stubbed
  until Phase 5 lands — the renderer is functional, the apply is
  best-effort and skipped when ``kubectl`` isn't on PATH.

Hard-rule reminder: targets persist their own :class:`BotDeployment`
row. The :class:`BotRuntime` may also write a sibling row for end-to-end
correlation; both rows reference the same ``BotVersion`` snapshot.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class BotDeploymentResult:
    """Outcome of a target dispatch."""

    deployment_id: str | None
    target: str
    status: str
    started_at: float
    bot_id: str | None = None
    bot_slug: str | None = None
    duration_ms: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)
    manifest_yaml: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeploymentTarget(ABC):
    """Strategy interface for one deployment backend."""

    name: str = "base"

    @abstractmethod
    def deploy(self, bot: Any, *, overrides: dict[str, Any]) -> BotDeploymentResult:  # pragma: no cover - ABC
        ...


class PaperSessionTarget(DeploymentTarget):
    """Launch the bot's paper session in-process and persist a deployment row.

    For background execution (the typical Celery path) call
    :func:`aqp.tasks.bot_tasks.run_bot_paper` instead so the session
    runs inside the Celery worker and ``/chat/stream/<task_id>``
    receives live updates.
    """

    name = "paper_session"

    def deploy(self, bot: Any, *, overrides: dict[str, Any]) -> BotDeploymentResult:
        import time

        started = time.time()
        deployment_id = _open_deployment_row(bot, target=self.name)
        try:
            session = bot.paper(**overrides)
            result = asyncio.run(session.run())
            payload = asdict(result) if hasattr(result, "__dataclass_fields__") else dict(result)
            status = payload.get("status", "completed")
            _finalise_deployment_row(deployment_id, status=status, result=payload)
            return BotDeploymentResult(
                deployment_id=deployment_id,
                target=self.name,
                status=status,
                started_at=started,
                bot_id=getattr(bot, "bot_id", None),
                bot_slug=bot.spec.slug,
                duration_ms=(time.time() - started) * 1000.0,
                result=payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("PaperSessionTarget.deploy failed")
            _finalise_deployment_row(deployment_id, status="error", result={}, error=str(exc))
            return BotDeploymentResult(
                deployment_id=deployment_id,
                target=self.name,
                status="error",
                started_at=started,
                bot_id=getattr(bot, "bot_id", None),
                bot_slug=bot.spec.slug,
                duration_ms=(time.time() - started) * 1000.0,
                error=str(exc),
            )


class BacktestOnlyTarget(DeploymentTarget):
    """Run a single backtest as the deployment artefact (no long-running process)."""

    name = "backtest_only"

    def deploy(self, bot: Any, *, overrides: dict[str, Any]) -> BotDeploymentResult:
        import time

        started = time.time()
        deployment_id = _open_deployment_row(bot, target=self.name)
        try:
            run_name = overrides.pop("run_name", None) if isinstance(overrides, dict) else None
            payload = bot.backtest(run_name=run_name, **overrides)
            _finalise_deployment_row(deployment_id, status="completed", result=payload)
            return BotDeploymentResult(
                deployment_id=deployment_id,
                target=self.name,
                status="completed",
                started_at=started,
                bot_id=getattr(bot, "bot_id", None),
                bot_slug=bot.spec.slug,
                duration_ms=(time.time() - started) * 1000.0,
                result=payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("BacktestOnlyTarget.deploy failed")
            _finalise_deployment_row(deployment_id, status="error", result={}, error=str(exc))
            return BotDeploymentResult(
                deployment_id=deployment_id,
                target=self.name,
                status="error",
                started_at=started,
                bot_id=getattr(bot, "bot_id", None),
                bot_slug=bot.spec.slug,
                duration_ms=(time.time() - started) * 1000.0,
                error=str(exc),
            )


class KubernetesTarget(DeploymentTarget):
    """Render a Kubernetes Deployment + ConfigMap manifest for the bot.

    Layout (one file per bot, kept under version control):

    ::

        deploy/k8s/bots/<slug>.yaml

    The manifest is best-effort applied with ``kubectl apply -f`` when
    that binary is on PATH. Otherwise the manifest is simply persisted
    onto the :class:`BotDeployment` row so a CI job (Argo workflow,
    etc.) can apply it later.
    """

    name = "kubernetes"

    def __init__(self, *, manifest_root: Path | None = None, apply: bool = False) -> None:
        self.manifest_root = manifest_root or _default_manifest_root()
        self.apply = apply

    def deploy(self, bot: Any, *, overrides: dict[str, Any]) -> BotDeploymentResult:
        import time

        started = time.time()
        deployment_id = _open_deployment_row(bot, target=self.name)
        try:
            manifest = self.render_manifest(bot, overrides=overrides)
            target_path = self.manifest_root / f"{bot.spec.slug}.yaml"
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(manifest, encoding="utf-8")

            applied: dict[str, Any] = {"applied": False, "manifest_path": str(target_path)}
            if self.apply and shutil.which("kubectl"):
                try:
                    proc = subprocess.run(
                        ["kubectl", "apply", "-f", str(target_path)],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    applied = {
                        "applied": True,
                        "manifest_path": str(target_path),
                        "stdout": proc.stdout.strip(),
                    }
                except subprocess.CalledProcessError as exc:
                    applied = {
                        "applied": False,
                        "manifest_path": str(target_path),
                        "stderr": exc.stderr.strip(),
                    }

            _finalise_deployment_row(
                deployment_id,
                status="completed",
                result=applied,
                manifest_yaml=manifest,
            )
            return BotDeploymentResult(
                deployment_id=deployment_id,
                target=self.name,
                status="completed",
                started_at=started,
                bot_id=getattr(bot, "bot_id", None),
                bot_slug=bot.spec.slug,
                duration_ms=(time.time() - started) * 1000.0,
                result=applied,
                manifest_yaml=manifest,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("KubernetesTarget.deploy failed")
            _finalise_deployment_row(deployment_id, status="error", result={}, error=str(exc))
            return BotDeploymentResult(
                deployment_id=deployment_id,
                target=self.name,
                status="error",
                started_at=started,
                bot_id=getattr(bot, "bot_id", None),
                bot_slug=bot.spec.slug,
                duration_ms=(time.time() - started) * 1000.0,
                error=str(exc),
            )

    def render_manifest(self, bot: Any, *, overrides: dict[str, Any]) -> str:
        """Render the bot to a Deployment + ConfigMap YAML document.

        The pod runs ``python -m aqp.bots.cli run <slug>`` which the
        Phase 5 CLI will provide. Until then the rendered manifest is
        a deployable artefact a cluster operator can edit by hand.
        """
        spec = bot.spec
        deployment_spec = spec.deployment
        namespace = (overrides or {}).get("namespace") or deployment_spec.namespace
        image = (overrides or {}).get("image") or deployment_spec.image or "ghcr.io/aqp/bot-runner:latest"
        resources = deployment_spec.resources or {
            "requests": {"cpu": "200m", "memory": "256Mi"},
            "limits": {"cpu": "1", "memory": "1Gi"},
        }

        configmap = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": f"bot-{spec.slug}-spec",
                "namespace": namespace,
                "labels": _bot_labels(bot),
            },
            "data": {"bot.yaml": spec.to_yaml()},
        }
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": f"bot-{spec.slug}",
                "namespace": namespace,
                "labels": _bot_labels(bot),
            },
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": f"bot-{spec.slug}"}},
                "template": {
                    "metadata": {"labels": _bot_labels(bot, include_app=True)},
                    "spec": {
                        "containers": [
                            {
                                "name": "bot",
                                "image": image,
                                "args": ["python", "-m", "aqp.bots.cli", "run", spec.slug],
                                "env": [
                                    {"name": "AQP_BOT_SLUG", "value": spec.slug},
                                ],
                                "resources": resources,
                                "volumeMounts": [
                                    {"name": "spec", "mountPath": "/etc/aqp/bot"},
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "spec",
                                "configMap": {"name": f"bot-{spec.slug}-spec"},
                            }
                        ],
                    },
                },
            },
        }
        documents = [configmap, deployment]
        return yaml.safe_dump_all(documents, sort_keys=False)


class DeploymentDispatcher:
    """Pick the right :class:`DeploymentTarget` for a bot.

    Targets are looked up by spec key (``paper_session``, ``kubernetes``,
    ``backtest_only``). Custom targets can be registered via
    :meth:`register`.
    """

    def __init__(self) -> None:
        self._targets: dict[str, DeploymentTarget] = {
            PaperSessionTarget.name: PaperSessionTarget(),
            BacktestOnlyTarget.name: BacktestOnlyTarget(),
            KubernetesTarget.name: KubernetesTarget(),
        }

    def register(self, target: DeploymentTarget) -> None:
        self._targets[target.name] = target

    def deploy(
        self,
        bot: Any,
        *,
        target: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> BotDeploymentResult:
        chosen = (target or bot.spec.deployment.target).lower()
        if chosen not in self._targets:
            raise ValueError(
                f"Unknown deployment target {chosen!r}; options: {sorted(self._targets)}"
            )
        return self._targets[chosen].deploy(bot, overrides=overrides or {})


# ----------------------------------------------------------------- helpers


def _bot_labels(bot: Any, *, include_app: bool = False) -> dict[str, str]:
    spec = bot.spec
    labels = {
        "app.kubernetes.io/name": "aqp-bot",
        "app.kubernetes.io/instance": spec.slug,
        "aqp.io/bot-slug": spec.slug,
        "aqp.io/bot-kind": spec.kind,
    }
    if include_app:
        labels["app"] = f"bot-{spec.slug}"
    if bot.project_id:
        labels["aqp.io/project-id"] = str(bot.project_id)
    return labels


def _default_manifest_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "deploy" / "k8s" / "bots"


def _open_deployment_row(bot: Any, *, target: str) -> str | None:
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_bots import Bot as BotRow
        from aqp.persistence.models_bots import BotDeployment

        with SessionLocal() as session:
            bot_row = (
                session.query(BotRow)
                .filter(BotRow.slug == bot.spec.slug)
                .one_or_none()
            )
            row = BotDeployment(
                id=str(uuid.uuid4()),
                bot_id=bot_row.id if bot_row is not None else None,
                target=target,
                status="running",
                started_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            return row.id
    except Exception:  # noqa: BLE001
        logger.debug("Could not open bot_deployment row from target", exc_info=True)
        return None


def _finalise_deployment_row(
    deployment_id: str | None,
    *,
    status: str,
    result: dict[str, Any],
    error: str | None = None,
    manifest_yaml: str | None = None,
) -> None:
    if deployment_id is None:
        return
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_bots import BotDeployment

        with SessionLocal() as session:
            row = session.get(BotDeployment, deployment_id)
            if row is None:
                return
            row.status = status
            row.result_summary = result
            row.error = error
            row.ended_at = datetime.utcnow()
            if manifest_yaml is not None:
                row.manifest_yaml = manifest_yaml
    except Exception:  # noqa: BLE001
        logger.debug("Could not finalise bot_deployment row from target", exc_info=True)


__all__ = [
    "BacktestOnlyTarget",
    "BotDeploymentResult",
    "DeploymentDispatcher",
    "DeploymentTarget",
    "KubernetesTarget",
    "PaperSessionTarget",
]
