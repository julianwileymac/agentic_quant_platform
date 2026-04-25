"""`aqp serve <backend> <model-uri>` CLI.

Registered through :mod:`aqp.cli.main` so ``aqp serve ...`` is available
out of the box.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import typer

from aqp.mlops.serving.base import resolve_model

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="serve",
    help="Serve a trained model via MLflow Serve, Ray Serve, or TorchServe.",
    no_args_is_help=True,
)


def _print(info: Any) -> None:
    typer.echo(json.dumps(info.__dict__, default=str, indent=2))


@app.command("mlflow")
def serve_mlflow(
    model_uri: str = typer.Argument(..., help="Model URI (path, runs:/... or models:/...)"),
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(5001, "--port"),
    workers: int = typer.Option(1, "--workers"),
    env_manager: str = typer.Option("local", "--env-manager"),
) -> None:
    """Spawn ``mlflow models serve`` behind an HTTP endpoint."""
    from aqp.mlops.serving.mlflow_serve import MLflowServeDeployment

    deployer = MLflowServeDeployment(
        host=host,
        port=port,
        workers=workers,
        env_manager=env_manager,
    )
    info = deployer.deploy(resolve_model(model_uri))
    _print(info)


@app.command("ray")
def serve_ray(
    model_uri: str = typer.Argument(...),
    name: str = typer.Option("aqp-model", "--name"),
    route_prefix: str = typer.Option("/aqp", "--route-prefix"),
    num_replicas: int = typer.Option(1, "--num-replicas"),
    ray_address: str = typer.Option("auto", "--ray-address"),
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Deploy the model via ``ray.serve``."""
    from aqp.mlops.serving.ray_serve import RayServeDeployment

    deployer = RayServeDeployment(
        ray_address=ray_address,
        route_prefix=route_prefix,
        name=name,
        http_host=host,
        http_port=port,
        num_replicas=num_replicas,
    )
    info = deployer.deploy(resolve_model(model_uri))
    _print(info)


@app.command("torchserve")
def serve_torchserve(
    model_uri: str = typer.Argument(...),
    model_name: str = typer.Option("aqp-model", "--model-name"),
    version: str = typer.Option("1.0", "--version"),
    inference_url: str = typer.Option("http://localhost:8080", "--inference-url"),
    management_url: str = typer.Option("http://localhost:8081", "--management-url"),
    initial_workers: int = typer.Option(1, "--initial-workers"),
    batch_size: int = typer.Option(1, "--batch-size"),
    max_batch_delay_ms: int = typer.Option(100, "--max-batch-delay-ms"),
    handler: str = typer.Option(None, "--handler", help="Custom handler .py; defaults to AQP's PreprocessingSpec-aware handler."),
) -> None:
    """Package + register the model with TorchServe."""
    from aqp.mlops.serving.torchserve import TorchServeDeployment

    deployer = TorchServeDeployment(
        inference_url=inference_url,
        management_url=management_url,
        handler=handler,
        batch_size=batch_size,
        max_batch_delay_ms=max_batch_delay_ms,
        initial_workers=initial_workers,
    )
    info = deployer.deploy(
        resolve_model(model_uri),
        model_name=model_name,
        version=version,
    )
    _print(info)


if __name__ == "__main__":  # pragma: no cover
    app()
