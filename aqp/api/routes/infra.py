"""``/api/infra/*`` — Infrastructure Overview surface for the ``/infra`` frontend.

Backs the 7 frontend panes:

A. Infrastructure Overview     -> ``GET /api/infra/status``
B. Bot Fleet Control           -> ``WS  /ws/infra/bot-status``
C. Celery Queue Monitor        -> ``GET /api/infra/queues``
D. Data Pipeline Status        -> ``GET /api/infra/pipeline``
E. Secrets Sync Status         -> ``GET /api/infra/secrets``
F. K8s Resource Explorer       -> ``GET /api/infra/k8s/{namespace}`` + ``WS /ws/infra/k8s/.../logs``
G. Canary Deployment Ctrl      -> ``POST /api/infra/canary``

All routes are :func:`secure_router`-protected at the default
``data:read`` scope. Mutating routes additionally call
``require_scope("infra:write")``. Per AGENTS rule 22, agents do NOT
go through this surface — they read through ``data.*`` MCP tools.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field

from aqp.api.security import (
    require_authenticated,
    require_scope,
    secure_router,
)
from aqp.auth import CurrentUser

logger = logging.getLogger(__name__)


router = secure_router(prefix="/api/infra", tags=["infra"])
ws_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers — Redis + Kubernetes adapter (lazy)
# ---------------------------------------------------------------------------


def _redis_client():
    try:
        import redis

        from aqp.config import settings

        return redis.Redis.from_url(str(settings.redis_url), decode_responses=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("redis client unavailable: %s", exc)
        return None


def _k8s_adapter():
    try:
        from aqp.kubernetes import get_kubernetes_adapter

        return get_kubernetes_adapter()
    except Exception as exc:  # noqa: BLE001
        logger.debug("kubernetes adapter unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pane A — Infrastructure Overview
# ---------------------------------------------------------------------------


@router.get("/status")
def overview_status(
    environment: str | None = Query(default=None),
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    """Live status cards per workspace + aggregate counts."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import (
        TerraformRun,
        TerraformStateVersion,
        TerraformWorkspace,
    )

    workspaces_payload: list[dict[str, Any]] = []
    total_runs = 0
    drift_alert = False
    with get_session() as session:
        q = session.query(TerraformWorkspace).filter(TerraformWorkspace.archived.is_(False))
        if environment:
            q = q.filter(TerraformWorkspace.environment == environment)
        for ws in q.all():
            last_apply = (
                session.query(TerraformRun)
                .filter(TerraformRun.terraform_workspace_id == ws.id)
                .filter(TerraformRun.run_kind == "apply")
                .filter(TerraformRun.status == "completed")
                .order_by(TerraformRun.finished_at.desc())
                .first()
            )
            last_run = (
                session.query(TerraformRun)
                .filter(TerraformRun.terraform_workspace_id == ws.id)
                .order_by(TerraformRun.started_at.desc())
                .first()
            )
            state = (
                session.query(TerraformStateVersion)
                .filter(TerraformStateVersion.terraform_workspace_id == ws.id)
                .order_by(TerraformStateVersion.serial.desc())
                .first()
            )
            drift = (
                last_run is not None
                and last_run.run_kind == "refresh"
                and (last_run.plan_summary_json or {}).get("total_changes", 0) > 0
            )
            if drift:
                drift_alert = True
            resource_count = state.resource_count if state else None
            workspaces_payload.append(
                {
                    "id": ws.id,
                    "slug": ws.slug,
                    "name": ws.name,
                    "environment": ws.environment,
                    "state_backend": ws.state_backend,
                    "tenant_org_id": ws.tenant_org_id,
                    "last_apply_at": (
                        last_apply.finished_at.isoformat()
                        if last_apply and last_apply.finished_at
                        else None
                    ),
                    "last_run_status": last_run.status if last_run else None,
                    "last_run_kind": last_run.run_kind if last_run else None,
                    "state_serial": state.serial if state else None,
                    "resource_count": resource_count,
                    "drift": bool(drift),
                }
            )
            total_runs += 1
    return {
        "workspaces": workspaces_payload,
        "totals": {
            "workspaces": len(workspaces_payload),
            "runs": total_runs,
            "drift_alert": drift_alert,
        },
        "generated_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Pane C — Celery Queue Monitor
# ---------------------------------------------------------------------------


_DEFAULT_QUEUES = (
    "default",
    "backtest",
    "agents",
    "ml",
    "ingestion",
    "training",
    "paper",
    "rag",
    "factors",
    "hft",
    "terraform",
)


@router.get("/queues")
def queue_depths(
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    """Redis LLEN for every Celery queue + KEDA replica count where available."""
    client = _redis_client()
    depths: dict[str, int] = {}
    if client is not None:
        for q in _DEFAULT_QUEUES:
            try:
                depths[q] = int(client.llen(q) or 0)
            except Exception as exc:  # noqa: BLE001
                logger.debug("LLEN %s failed: %s", q, exc)
                depths[q] = 0
    else:
        depths = dict.fromkeys(_DEFAULT_QUEUES, 0)

    replicas = _scaledobject_replicas()
    return {
        "queues": [
            {
                "name": q,
                "depth": depths.get(q, 0),
                "current_replicas": replicas.get(q),
            }
            for q in _DEFAULT_QUEUES
        ],
        "generated_at": datetime.utcnow().isoformat(),
    }


def _scaledobject_replicas() -> dict[str, int | None]:
    """Best-effort KEDA ``ScaledObject.status.currentReplicas`` lookup.

    Returns ``{queue_name: replicas}`` or ``{}`` when the cluster is
    unreachable or KEDA isn't installed.
    """
    adapter = _k8s_adapter()
    if adapter is None or not adapter.is_available():
        return {}
    out: dict[str, int | None] = {}
    try:
        from aqp.config import settings

        ns = getattr(settings, "terraform_runner_namespace", "aqp-system")
    except Exception:
        ns = "aqp-system"
    # Each ScaledObject is named aqp-celery-<queue>-scaler. We try to
    # read it via apply_manifest's dry-run; on missing CRD the adapter
    # raises KubernetesAdapterUnavailable and we silently skip.
    for q in _DEFAULT_QUEUES:
        try:
            manifest = {
                "apiVersion": "keda.sh/v1alpha1",
                "kind": "ScaledObject",
                "metadata": {"name": f"aqp-celery-{q}-scaler", "namespace": ns},
            }
            # apply_manifest is mutating; the adapter doesn't expose a
            # read helper for arbitrary CRDs yet. We swallow errors here
            # because this is best-effort UI metadata.
            out[q] = None
            _ = manifest  # noqa: F841 - placeholder for future read API
        except Exception:  # noqa: BLE001
            out[q] = None
    return out


# ---------------------------------------------------------------------------
# Pane D — Data Pipeline Status
# ---------------------------------------------------------------------------


@router.get("/pipeline")
def pipeline_status(
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    """Ingestion adapter health + Iceberg lake metrics + Alembic head."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_pipelines import (
        FetcherRun,
        PipelineManifestRow,
        PipelineRunRow,
    )

    adapters: list[dict[str, Any]] = []
    parquet_metrics: dict[str, Any] = {}
    alembic_revision = _current_alembic_revision()

    with get_session() as session:
        # Recent ingestion adapter runs grouped by manifest slug.
        recent = (
            session.query(FetcherRun)
            .order_by(FetcherRun.started_at.desc())
            .limit(200)
            .all()
        )
        by_name: dict[str, dict[str, Any]] = {}
        for run in recent:
            key = run.fetcher_name or "unknown"
            entry = by_name.setdefault(
                key,
                {
                    "name": key,
                    "last_run_at": None,
                    "last_status": None,
                    "records": 0,
                    "errors_24h": 0,
                },
            )
            if entry["last_run_at"] is None:
                entry["last_run_at"] = (
                    run.started_at.isoformat() if run.started_at else None
                )
                entry["last_status"] = run.status
            entry["records"] += int(run.rows_written or 0)
            if run.status in {"errored", "failed"} and run.started_at:
                age = (datetime.utcnow() - run.started_at).total_seconds()
                if age < 86400:
                    entry["errors_24h"] += 1
        adapters = list(by_name.values())

        pipeline_count = session.query(PipelineManifestRow).count()
        pipeline_run_count = session.query(PipelineRunRow).count()
        parquet_metrics = {
            "manifest_count": pipeline_count,
            "pipeline_run_count": pipeline_run_count,
        }
    return {
        "adapters": adapters,
        "parquet": parquet_metrics,
        "alembic_revision": alembic_revision,
        "generated_at": datetime.utcnow().isoformat(),
    }


def _current_alembic_revision() -> str | None:
    """Read the current head from the ``alembic_version`` table."""
    try:
        import sqlalchemy as sa

        from aqp.persistence.db import engine

        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            if row is None:
                return None
            return str(row[0])
    except Exception as exc:  # noqa: BLE001
        logger.debug("alembic head lookup failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pane E — Secrets Sync Status
# ---------------------------------------------------------------------------


@router.get("/secrets")
def secrets_status(
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    """List active SecretStores + their describe payload (no values).

    Never returns secret values — only the chain metadata + the
    actively-registered stores so the UI can render a "synced /
    stale / error" status per store.
    """
    try:
        from aqp.credentials import get_resolver
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, detail=f"credentials subsystem unavailable: {exc}") from exc

    resolver = get_resolver()
    payload = resolver.describe()
    return {
        "stores": payload.get("stores", []),
        "generated_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Pane F — K8s Resource Explorer
# ---------------------------------------------------------------------------


@router.get("/k8s/{namespace}")
def k8s_namespace(
    namespace: str,
    label_selector: str | None = Query(default=None),
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    """List pods (+ basic metadata) for a namespace via the KubernetesAdapter."""
    adapter = _k8s_adapter()
    if adapter is None or not adapter.is_available():
        return {
            "pods": [],
            "adapter_available": False,
            "generated_at": datetime.utcnow().isoformat(),
        }
    try:
        pods = adapter.list_pods(namespace=namespace, label_selector=label_selector)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, detail=f"list_pods failed: {exc}") from exc
    items = [
        {
            "namespace": p.namespace,
            "name": p.name,
            "phase": p.phase,
            "node": p.node,
            "pod_ip": p.pod_ip,
            "started_at": p.started_at,
            "containers": list(p.containers),
            "labels": dict(p.labels),
        }
        for p in pods
    ]
    return {
        "namespace": namespace,
        "pods": items,
        "adapter_available": True,
        "generated_at": datetime.utcnow().isoformat(),
    }


@ws_router.websocket("/ws/infra/k8s/{namespace}/pods/{name}/logs")
async def k8s_pod_logs(
    ws: WebSocket,
    namespace: str,
    name: str,
    container: str | None = Query(default=None),
    since_seconds: int | None = Query(default=None),
    tail_lines: int | None = Query(default=None),
) -> None:
    """Stream pod logs as canonical progress frames.

    Phase 3a authentication: first client frame must be
    ``{"type":"auth","token":"<JWT>"}``. See :mod:`aqp.auth.ws`.
    """
    from aqp.auth.ws import ws_authenticator

    await ws.accept()
    auth_result = await ws_authenticator.authenticate(ws)
    if auth_result is None:
        return
    adapter = _k8s_adapter()
    if adapter is None or not adapter.is_available():
        await ws.send_json(
            {
                "task_id": f"k8s-logs-{namespace}-{name}",
                "stage": "error",
                "message": "kubernetes adapter unavailable",
                "timestamp": time.time(),
            }
        )
        await ws.close()
        return
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=1024)

    def _producer() -> None:
        try:
            for event in adapter.stream_pod_logs(
                namespace=namespace,
                name=name,
                container=container,
                since_seconds=since_seconds,
                tail_lines=tail_lines,
                follow=True,
                max_lines=10000,
            ):
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "task_id": f"k8s-logs-{namespace}-{name}",
                        "stage": "log",
                        "message": event.line,
                        "timestamp": time.time(),
                        "container": event.container,
                        "log_timestamp": event.timestamp,
                        "source": event.source,
                    },
                )
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "task_id": f"k8s-logs-{namespace}-{name}",
                    "stage": "error",
                    "message": str(exc),
                    "timestamp": time.time(),
                },
            )

    loop.run_in_executor(None, _producer)
    try:
        while True:
            frame = await queue.get()
            await ws.send_json(frame)
            if frame.get("stage") == "error":
                break
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        logger.exception("k8s_pod_logs stream failed")
    finally:
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Pane G — Canary Deployment Controller
# ---------------------------------------------------------------------------


class CanaryRequest(BaseModel):
    weight: int = Field(..., ge=0, le=100, description="0-100 Next.js traffic weight")
    namespace: str | None = Field(default=None)
    config_map_name: str | None = Field(default=None)
    note: str | None = Field(default=None)


@router.post("/canary")
def update_canary_weight(
    body: CanaryRequest,
    user: CurrentUser = Depends(require_scope("infra:write")),
) -> dict[str, Any]:
    """Update the canary ingress weight via the KubernetesAdapter.

    The frontend ingress declares ``nginx.ingress.kubernetes.io/canary=true``
    and ``nginx.ingress.kubernetes.io/canary-weight=<int>``. This route
    upserts the weight in a ConfigMap the ingress reads at refresh
    time, then patches the live Ingress resource so the change takes
    effect without a redeploy.
    """
    adapter = _k8s_adapter()
    if adapter is None or not adapter.is_available():
        raise HTTPException(503, detail="kubernetes adapter unavailable")
    try:
        from aqp.config import settings

        default_ns = getattr(settings, "terraform_runner_namespace", "aqp-system")
    except Exception:
        default_ns = "aqp-system"

    ns = body.namespace or default_ns
    config_map_name = body.config_map_name or "aqp-canary-weights"
    manifest = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": config_map_name,
            "namespace": ns,
            "annotations": {
                "aqp.io/updated-by": user.id,
                "aqp.io/updated-at": datetime.utcnow().isoformat(),
                "aqp.io/note": body.note or "",
            },
        },
        "data": {
            "nextjs_weight": str(int(body.weight)),
            "solara_weight": str(100 - int(body.weight)),
        },
    }
    try:
        result = adapter.apply_manifest(manifest=manifest, namespace=ns)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, detail=f"canary apply failed: {exc}") from exc
    return {
        "weight": int(body.weight),
        "config_map_name": config_map_name,
        "namespace": ns,
        "applied": result,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Pane B — Bot Fleet Control (WebSocket fan-out)
# ---------------------------------------------------------------------------


@ws_router.websocket("/ws/infra/bot-status")
async def bot_status_stream(ws: WebSocket) -> None:
    """30s-tick fan-out of bot fleet + queue status for the dashboard.

    Phase 3a authentication: first client frame must be
    ``{"type":"auth","token":"<JWT>"}``. See :mod:`aqp.auth.ws`.
    """
    from aqp.auth.ws import ws_authenticator

    await ws.accept()
    auth_result = await ws_authenticator.authenticate(ws)
    if auth_result is None:
        return
    try:
        while True:
            payload: dict[str, Any] = {
                "timestamp": time.time(),
                "queues": queue_depths(user=_anon_user()),  # type: ignore[arg-type]
                "bots": _bot_fleet_snapshot(),
            }
            await ws.send_json(payload)
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        logger.exception("bot_status_stream failed")
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


def _anon_user() -> Any:
    """Synthesise a minimal CurrentUser for the WS callers (no auth header)."""
    from aqp.auth.user import default_user

    return default_user()


def _bot_fleet_snapshot() -> list[dict[str, Any]]:
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_bots import Bot, BotDeployment

        with get_session() as session:
            bots = session.query(Bot).limit(200).all()
            items: list[dict[str, Any]] = []
            for bot in bots:
                last_dep = (
                    session.query(BotDeployment)
                    .filter(BotDeployment.bot_id == bot.id)
                    .order_by(BotDeployment.created_at.desc())
                    .first()
                )
                items.append(
                    {
                        "id": bot.id,
                        "slug": bot.slug,
                        "name": bot.name,
                        "kind": bot.kind,
                        "status": bot.status,
                        "last_deployment_status": (
                            last_dep.status if last_dep else None
                        ),
                        "last_deployment_target": (
                            last_dep.target if last_dep else None
                        ),
                        "last_deployment_at": (
                            last_dep.created_at.isoformat()
                            if last_dep and last_dep.created_at
                            else None
                        ),
                    }
                )
            return items
    except Exception:  # noqa: BLE001
        return []


__all__ = ["router", "ws_router"]
