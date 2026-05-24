"""`aqp-cli cp` — control-plane day-2 operations."""

from __future__ import annotations

from typing import Any

import httpx
import typer

from aqp_cli.commands._common import control_plane_client, exit_for_http_error, monolith_client
from aqp_cli.ui.output import render_json

app = typer.Typer(name="cp", help="AQP control-plane operations.", no_args_is_help=True)
deployments_app = typer.Typer(help="Manage workloads through /manage/deployments.")
workloads_app = typer.Typer(help="Global workload operations.")
cluster_app = typer.Typer(help="Kubernetes pod helpers through /cluster.")
terraform_app = typer.Typer(help="TerraformRuntime operations through /terraform.")
cloudflare_app = typer.Typer(help="Cloudflare edge operations through /cloudflare.")
topology_app = typer.Typer(help="Topology metadata operations.")

app.add_typer(deployments_app, name="deployments")
app.add_typer(workloads_app, name="workloads")
app.add_typer(cluster_app, name="cluster")
app.add_typer(terraform_app, name="terraform")
app.add_typer(cloudflare_app, name="cloudflare")
app.add_typer(topology_app, name="topology")


def _cp_request(
    method: str, path: str, *, params: dict[str, Any] | None = None, json_body: Any | None = None
) -> None:
    client = control_plane_client(require_token=True)
    try:
        render_json(client.request(method, path, params=params, json_body=json_body))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


def _api_request(
    method: str, path: str, *, params: dict[str, Any] | None = None, json_body: Any | None = None
) -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request(method, path, params=params, json_body=json_body))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@deployments_app.command("list")
def deployments_list(namespace: str = typer.Option("", "--namespace")) -> None:
    params = {"namespace": namespace} if namespace else None
    _cp_request("GET", "/manage/deployments", params=params)


@deployments_app.command("status")
def deployments_status(service_id: str, namespace: str = typer.Option("", "--namespace")) -> None:
    params = {"namespace": namespace} if namespace else None
    _cp_request("GET", f"/manage/deployments/{service_id}", params=params)


@deployments_app.command("start")
def deployments_start(
    service_id: str,
    image: str = typer.Option("", "--image"),
    namespace: str = typer.Option("", "--namespace"),
    replicas: int = typer.Option(1, "--replicas"),
) -> None:
    body: dict[str, Any] = {
        "service_id": service_id,
        "image": image or "",
        "replicas": replicas,
    }
    if namespace:
        body["namespace"] = namespace
    _cp_request("POST", f"/manage/deployments/{service_id}/start", json_body=body)


@deployments_app.command("stop")
def deployments_stop(service_id: str, namespace: str = typer.Option("", "--namespace")) -> None:
    params = {"namespace": namespace} if namespace else None
    _cp_request("POST", f"/manage/deployments/{service_id}/stop", params=params)


@deployments_app.command("scale")
def deployments_scale(
    service_id: str, replicas: int, namespace: str = typer.Option("", "--namespace")
) -> None:
    params: dict[str, Any] = {"replicas": replicas}
    if namespace:
        params["namespace"] = namespace
    _cp_request("PATCH", f"/manage/deployments/{service_id}/scale", params=params)


@deployments_app.command("restart")
def deployments_restart(service_id: str, namespace: str = typer.Option("", "--namespace")) -> None:
    params = {"namespace": namespace} if namespace else None
    _cp_request("POST", f"/manage/deployments/{service_id}/restart", params=params)


@deployments_app.command("exec")
def deployments_exec(
    service_id: str,
    command: list[str] = typer.Argument(..., help="Command tokens to execute."),  # noqa: B008
    namespace: str = typer.Option("", "--namespace"),
    container: str = typer.Option("", "--container"),
    timeout_seconds: int = typer.Option(60, "--timeout-seconds"),
) -> None:
    body: dict[str, Any] = {
        "command": command,
        "timeout_seconds": timeout_seconds,
    }
    if namespace:
        body["namespace"] = namespace
    if container:
        body["container"] = container
    _cp_request("POST", f"/manage/deployments/{service_id}/exec", json_body=body)


@deployments_app.command("logs")
def deployments_logs(
    service_id: str,
    namespace: str = typer.Option("", "--namespace"),
    container: str = typer.Option("", "--container"),
    tail: int = typer.Option(200, "--tail"),
) -> None:
    params: dict[str, Any] = {"tail": tail}
    if namespace:
        params["namespace"] = namespace
    if container:
        params["container"] = container
    _cp_request("GET", f"/manage/deployments/{service_id}/logs", params=params)


@workloads_app.command("halt-all")
def workloads_halt_all(reason: str = typer.Option("cli", "--reason")) -> None:
    _cp_request("POST", "/manage/workloads/halt", json_body={"reason": reason})


@workloads_app.command("halt-status")
def workloads_halt_status() -> None:
    _cp_request("GET", "/manage/workloads/halt/status")


@cluster_app.command("pods")
def cluster_pods(namespace: str = typer.Option("aqp", "--namespace")) -> None:
    _api_request("GET", f"/cluster/pods/{namespace}")


@cluster_app.command("logs")
def cluster_logs(
    namespace: str,
    name: str,
    container: str = typer.Option("", "--container"),
    tail_lines: int = typer.Option(200, "--tail-lines"),
) -> None:
    params: dict[str, Any] = {"tail_lines": tail_lines}
    if container:
        params["container"] = container
    _api_request("GET", f"/cluster/pods/{namespace}/{name}/logs", params=params)


@terraform_app.command("workspaces")
def terraform_workspaces() -> None:
    _api_request("GET", "/terraform/workspaces")


@terraform_app.command("runs")
def terraform_runs() -> None:
    _api_request("GET", "/terraform/runs")


@terraform_app.command("plan")
def terraform_plan(workspace_id: str) -> None:
    _api_request(
        "POST",
        f"/terraform/workspaces/{workspace_id}/plan",
        json_body={"var_overrides": {}, "destroy_plan": False},
    )


@terraform_app.command("apply")
def terraform_apply(
    workspace_id: str, plan_run_id: str, note: str = typer.Option("", "--note")
) -> None:
    payload: dict[str, Any] = {"plan_run_id": plan_run_id}
    if note:
        payload["approver_note"] = note
    _api_request("POST", f"/terraform/workspaces/{workspace_id}/apply", json_body=payload)


@terraform_app.command("destroy")
def terraform_destroy(
    workspace_id: str,
    confirmation_phrase: str = typer.Option(..., "--confirm"),
    note: str = typer.Option("", "--note"),
) -> None:
    payload: dict[str, Any] = {"confirmation_phrase": confirmation_phrase}
    if note:
        payload["approver_note"] = note
    _api_request("POST", f"/terraform/workspaces/{workspace_id}/destroy", json_body=payload)


@terraform_app.command("cancel")
def terraform_cancel(run_id: str) -> None:
    _api_request("POST", f"/terraform/runs/{run_id}/cancel")


@cloudflare_app.command("status")
def cloudflare_status() -> None:
    _api_request("GET", "/cloudflare/health")


@cloudflare_app.command("tunnels")
def cloudflare_tunnels() -> None:
    _api_request("GET", "/cloudflare/tunnels")


@cloudflare_app.command("dns")
def cloudflare_dns(zone_id: str, name: str = typer.Option("", "--name")) -> None:
    params = {"name": name} if name else None
    _api_request("GET", f"/cloudflare/dns/{zone_id}/records", params=params)


@topology_app.command("snapshot")
def topology_snapshot(
    include_targets: bool = typer.Option(True, "--include-targets/--no-include-targets"),
) -> None:
    _cp_request("GET", "/manage/topology", params={"include_targets": include_targets})


@topology_app.command("services")
def topology_services(
    role: str = typer.Option("", "--role"), cluster: str = typer.Option("", "--cluster")
) -> None:
    params: dict[str, Any] = {}
    if role:
        params["role"] = role
    if cluster:
        params["cluster"] = cluster
    _cp_request("GET", "/manage/topology/services", params=params or None)
