"""``aqp cp`` — operator CLI for the AQP control plane.

This is the day-2 operations entrypoint. It calls the canonical REST
surfaces instead of importing providers directly:

- workload lifecycle -> ``aqp_control_plane`` ``/manage/*``
- cluster pods -> AQP API ``/cluster/*``
- Terraform IaC -> AQP API ``/terraform/*``
- Cloudflare edge -> AQP API ``/cloudflare/*``

Mutating operations remain audited by the receiving runtime
(``WorkloadRuntime`` or ``TerraformRuntime``). The CLI never prints
access tokens or secret payloads.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
import typer


app = typer.Typer(
    name="cp",
    help="AQP control-plane day-2 operations.",
    no_args_is_help=True,
)
deployments_app = typer.Typer(help="Manage workloads through /manage/deployments.")
workloads_app = typer.Typer(help="Global workload operations.")
cluster_app = typer.Typer(help="Kubernetes pod helpers through /cluster.")
terraform_app = typer.Typer(help="TerraformRuntime operations through /terraform.")
cloudflare_app = typer.Typer(help="Cloudflare edge operations through /cloudflare.")

app.add_typer(deployments_app, name="deployments")
app.add_typer(workloads_app, name="workloads")
app.add_typer(cluster_app, name="cluster")
app.add_typer(terraform_app, name="terraform")
app.add_typer(cloudflare_app, name="cloudflare")


def _cp_base() -> str:
    return os.environ.get("AQP_CONTROL_PLANE_URL", "http://127.0.0.1:9000").rstrip("/")


def _api_base() -> str:
    return os.environ.get("AQP_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _headers() -> dict[str, str]:
    token = os.environ.get("AQP_CP_TOKEN") or os.environ.get("AQP_ACCESS_TOKEN")
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _print_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _request(
    method: str,
    base: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
) -> Any:
    url = f"{base}{path}"
    try:
        with httpx.Client(timeout=30.0, headers=_headers()) as client:
            resp = client.request(method, url, params=params, json=json_body)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = resp.text
            typer.secho(f"{method} {url} failed: {resp.status_code}", fg=typer.colors.RED, err=True)
            _print_json(body)
            raise typer.Exit(resp.status_code)
        if not resp.content:
            return {}
        return resp.json()
    except httpx.RequestError as exc:
        typer.secho(f"{method} {url} failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(9000, help="Bind port."),
    reload: bool = typer.Option(False, help="Enable uvicorn reload."),
    log_level: str = typer.Option("info", help="Uvicorn log level."),
) -> None:
    """Run the aqp_control_plane sidecar API server."""
    import uvicorn

    uvicorn.run(
        "aqp_cp.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


@deployments_app.command("list")
def deployments_list(namespace: str | None = None) -> None:
    _print_json(_request("GET", _cp_base(), "/manage/deployments", params={"namespace": namespace}))


@deployments_app.command("status")
def deployments_status(service_id: str, namespace: str | None = None) -> None:
    _print_json(
        _request("GET", _cp_base(), f"/manage/deployments/{service_id}", params={"namespace": namespace})
    )


@deployments_app.command("stop")
def deployments_stop(service_id: str, namespace: str | None = None) -> None:
    _print_json(
        _request("POST", _cp_base(), f"/manage/deployments/{service_id}/stop", params={"namespace": namespace})
    )


@deployments_app.command("scale")
def deployments_scale(service_id: str, replicas: int, namespace: str | None = None) -> None:
    _print_json(
        _request(
            "PATCH",
            _cp_base(),
            f"/manage/deployments/{service_id}/scale",
            params={"replicas": replicas, "namespace": namespace},
        )
    )


@deployments_app.command("restart")
def deployments_restart(service_id: str, namespace: str | None = None) -> None:
    _print_json(
        _request("POST", _cp_base(), f"/manage/deployments/{service_id}/restart", params={"namespace": namespace})
    )


@deployments_app.command("exec")
def deployments_exec(
    service_id: str,
    command: list[str] = typer.Argument(..., help="Command tokens to execute."),
    namespace: str | None = None,
    container: str | None = None,
    timeout_seconds: int = 60,
) -> None:
    _print_json(
        _request(
            "POST",
            _cp_base(),
            f"/manage/deployments/{service_id}/exec",
            json_body={
                "command": command,
                "namespace": namespace,
                "container": container,
                "timeout_seconds": timeout_seconds,
            },
        )
    )


@deployments_app.command("logs")
def deployments_logs(
    service_id: str,
    namespace: str | None = None,
    container: str | None = None,
    tail: int = 200,
) -> None:
    _print_json(
        _request(
            "GET",
            _cp_base(),
            f"/manage/deployments/{service_id}/logs",
            params={"namespace": namespace, "container": container, "tail": tail},
        )
    )


@workloads_app.command("halt-all")
def workloads_halt_all(reason: str = "cli") -> None:
    _print_json(_request("POST", _cp_base(), "/manage/workloads/halt", json_body={"reason": reason}))


@cluster_app.command("pods")
def cluster_pods(namespace: str = "aqp") -> None:
    _print_json(_request("GET", _api_base(), f"/cluster/pods/{namespace}"))


@cluster_app.command("logs")
def cluster_logs(namespace: str, name: str, container: str | None = None, tail_lines: int = 200) -> None:
    _print_json(
        _request(
            "GET",
            _api_base(),
            f"/cluster/pods/{namespace}/{name}/logs",
            params={"container": container, "tail_lines": tail_lines},
        )
    )


@terraform_app.command("workspaces")
def terraform_workspaces() -> None:
    _print_json(_request("GET", _api_base(), "/terraform/workspaces"))


@terraform_app.command("runs")
def terraform_runs() -> None:
    _print_json(_request("GET", _api_base(), "/terraform/runs"))


@terraform_app.command("plan")
def terraform_plan(workspace_id: str) -> None:
    _print_json(
        _request(
            "POST",
            _api_base(),
            f"/terraform/workspaces/{workspace_id}/plan",
            json_body={"var_overrides": {}, "destroy_plan": False},
        )
    )


@terraform_app.command("apply")
def terraform_apply(workspace_id: str, plan_run_id: str, note: str | None = None) -> None:
    _print_json(
        _request(
            "POST",
            _api_base(),
            f"/terraform/workspaces/{workspace_id}/apply",
            json_body={"plan_run_id": plan_run_id, "approver_note": note},
        )
    )


@terraform_app.command("destroy")
def terraform_destroy(
    workspace_id: str,
    confirmation_phrase: str = typer.Option(..., "--confirm", help="Required confirmation phrase."),
    note: str | None = None,
) -> None:
    _print_json(
        _request(
            "POST",
            _api_base(),
            f"/terraform/workspaces/{workspace_id}/destroy",
            json_body={"confirmation_phrase": confirmation_phrase, "approver_note": note},
        )
    )


@terraform_app.command("cancel")
def terraform_cancel(run_id: str) -> None:
    _print_json(_request("POST", _api_base(), f"/terraform/runs/{run_id}/cancel"))


@cloudflare_app.command("status")
def cloudflare_status() -> None:
    _print_json(_request("GET", _api_base(), "/cloudflare/health"))


@cloudflare_app.command("tunnels")
def cloudflare_tunnels() -> None:
    _print_json(_request("GET", _api_base(), "/cloudflare/tunnels"))


@cloudflare_app.command("dns")
def cloudflare_dns(zone_id: str, name: str | None = None) -> None:
    _print_json(
        _request("GET", _api_base(), f"/cloudflare/dns/{zone_id}/records", params={"name": name})
    )


__all__ = ["app"]
