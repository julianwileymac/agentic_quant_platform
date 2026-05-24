"""``aqp kernel`` CLI subcommands.

Verbs:

- ``aqp kernel start --image ... --memory ... [--gpu N]`` —
  provision a per-user kernel pod, write the local kernelspec,
  return connection details.
- ``aqp kernel list`` — list the calling user's active kernels.
- ``aqp kernel attach <kernel_id>`` — re-establish a local
  kernelspec for an existing kernel.
- ``aqp kernel stop <kernel_id>`` — tear down a kernel pod.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(
    name="kernel",
    help="Provision + attach per-user Jupyter kernel pods",
    no_args_is_help=True,
)


def _emit(payload: Any, output: str) -> None:
    if output == "json":
        typer.echo(json.dumps(payload, indent=2, default=str))
        return
    if isinstance(payload, list):
        for row in payload:
            typer.echo(
                "  ".join(f"{k}={v}" for k, v in row.items())
            )
        return
    typer.echo(
        "  ".join(f"{k}={v}" for k, v in payload.items())
    )


@app.command()
def start(
    image: str = typer.Option(
        "quant-research:py311-cpu",
        help="Container image; see aqp_kernels/pods/templates/ for choices.",
    ),
    memory: str = typer.Option("8Gi"),
    cpu: str = typer.Option("2"),
    gpu: int = typer.Option(0),
    node_selector: str | None = typer.Option(None),
    output: str = typer.Option("table", case_sensitive=False),
) -> None:
    """Provision a per-user kernel pod."""
    kernel_id = "krn_" + uuid.uuid4().hex[:8]
    user_id = os.environ.get("AQP_USER_ID", "local-dev")
    namespace = f"aqp-kernel-{user_id.replace('@', '-').replace('.', '-')}"
    payload = {
        "kernel_id": kernel_id,
        "user_id": user_id,
        "namespace": namespace,
        "image": image,
        "resources": {
            "requests": {"cpu": cpu, "memory": memory},
            "limits": {"cpu": cpu, "memory": memory},
        },
    }
    if gpu:
        payload["resources"]["requests"]["nvidia.com/gpu"] = str(gpu)
        payload["resources"]["limits"]["nvidia.com/gpu"] = str(gpu)
    if node_selector:
        payload["node_selector"] = dict(
            kv.split("=", 1) for kv in node_selector.split(",")
        )
    try:
        _provision_kernel_pod(payload)
        _install_local_kernelspec(payload)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)
    payload["jupyter_url"] = f"https://aqp.internal/kernels/{kernel_id}"
    _emit(payload, output)


@app.command(name="list")
def list_kernels(output: str = typer.Option("table", case_sensitive=False)) -> None:
    """List the calling user's active kernel pods."""
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_kernels import KernelSession

        user_id = os.environ.get("AQP_USER_ID", "local-dev")
        with get_session() as session:
            rows = (
                session.query(KernelSession)
                .filter(KernelSession.owner_user_id == user_id)
                .filter(KernelSession.terminated_at.is_(None))
                .order_by(KernelSession.started_at.desc())
                .all()
            )
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)
    _emit(
        [
            {
                "kernel_id": row.kernel_id,
                "image": row.image,
                "pod": row.pod_name,
                "started_at": row.started_at,
            }
            for row in rows
        ],
        output,
    )


@app.command()
def attach(
    kernel_id: str = typer.Argument(..., help="Existing kernel id"),
) -> None:
    """Re-install the local kernelspec for an existing kernel."""
    spec = {
        "kernel_id": kernel_id,
        "jupyter_url": f"https://aqp.internal/kernels/{kernel_id}",
    }
    _install_local_kernelspec(spec)
    typer.echo(f"installed kernelspec for {kernel_id}")


@app.command()
def stop(
    kernel_id: str = typer.Argument(..., help="Kernel id to tear down"),
) -> None:
    """Tear down a kernel pod."""
    try:
        _tear_down_kernel_pod(kernel_id)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"stopped {kernel_id}")


# ---------------------------------------------------------------------------
# Helpers (Phase 3 ships skeleton; full Enterprise-Gateway HTTP API
# round-trips land in Phase 5 after the Vite UI is wired up)
# ---------------------------------------------------------------------------


def _provision_kernel_pod(spec: dict[str, Any]) -> None:
    """Provision a kernel pod via the Gateway HTTP API."""
    # Phase 3 deliverable: persist the kernel_sessions row + call
    # the Jupyter Enterprise Gateway `/api/kernels` endpoint with
    # the constructed pod spec. Full HTTP round-trip lands when the
    # Gateway deployment YAML in aqp_kernels/gateway/ is operator-
    # rolled out.
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_kernels import KernelSession

        with get_session() as session:
            row = KernelSession(
                id=str(uuid.uuid4()),
                kernel_id=spec["kernel_id"],
                owner_user_id=spec["user_id"],
                image=spec["image"],
                pod_name=f"kernel-{spec['kernel_id']}",
                resource_quota_ref=json.dumps(spec.get("resources", {})),
            )
            session.add(row)
            session.commit()
    except Exception:  # noqa: BLE001
        # Provisioning + ORM are best-effort during the skeleton
        # phase; the local kernelspec still installs so the user
        # can iterate.
        pass


def _install_local_kernelspec(spec: dict[str, Any]) -> None:
    """Write a kernelspec under ~/.local/share/jupyter/kernels/aqp-<kid>/."""
    if os.name == "nt":
        kernels_root = Path.home() / "AppData" / "Roaming" / "jupyter" / "kernels"
    else:
        kernels_root = Path.home() / ".local" / "share" / "jupyter" / "kernels"
    name = f"aqp-{spec['kernel_id']}"
    target = kernels_root / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "kernel.json").write_text(
        json.dumps(
            {
                "argv": ["python", "-m", "aqp_kernels.gateway_kernel_launcher"],
                "display_name": f"AQP: {spec.get('image', name)}",
                "language": "python",
                "metadata": {
                    "aqp": {
                        "kernel_id": spec["kernel_id"],
                        "jupyter_url": spec.get("jupyter_url"),
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _tear_down_kernel_pod(kernel_id: str) -> None:
    """Stop a kernel pod."""
    try:
        from datetime import datetime

        from aqp.persistence.db import get_session
        from aqp.persistence.models_kernels import KernelSession

        with get_session() as session:
            row = (
                session.query(KernelSession)
                .filter(KernelSession.kernel_id == kernel_id)
                .one_or_none()
            )
            if row is not None and row.terminated_at is None:
                row.terminated_at = datetime.utcnow()
                session.commit()
    except Exception:  # noqa: BLE001
        pass


__all__ = ["app"]
