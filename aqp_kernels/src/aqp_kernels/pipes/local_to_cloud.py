"""Dagster Pipes wrappers — local script targets cloud execution.

Two surfaces:

- :func:`local_pipes_context` — wraps a local script with
  :func:`dagster_pipes.open_dagster_pipes` so the local execution
  emits structured logs / asset materializations that the cloud
  orchestrator picks up.
- :func:`cloud_run_with_pipes` — the cloud side: run a
  :class:`PipesK8sClient` against the kernel image so the local
  script runs in the cluster with full RLS bucket accounting.

Per the published Dagster Pipes docs the canonical pattern is::

    @asset
    def my_asset(context, pipes_k8s_client: PipesK8sClient):
        return pipes_k8s_client.run(
            context=context,
            image="quant-research:py311-cuda",
            command=["python", "/scripts/my_script.py"],
        ).get_materialize_result()

This wrapper plugs in the AQP rate-limit env so the kernel pod
that runs the script debits the calling user's buckets.
"""
from __future__ import annotations

import contextlib
import logging
import os
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def local_pipes_context(
    *,
    asset_key: str | None = None,
) -> Iterator[Any]:
    """Wrap a local script with :func:`dagster_pipes.open_dagster_pipes`.

    Falls back to a no-op context when ``dagster_pipes`` isn't
    installed so the local script keeps running for ad-hoc /
    offline work.
    """
    try:
        from dagster_pipes import open_dagster_pipes
    except ImportError:
        logger.debug("dagster_pipes not installed; skipping pipes context")
        yield None
        return
    with open_dagster_pipes() as context:
        if asset_key:
            try:
                context.log.info(f"asset_key={asset_key}")
            except Exception:  # noqa: BLE001
                pass
        yield context


def cloud_run_with_pipes(
    *,
    image: str,
    command: list[str],
    env: dict[str, str] | None = None,
    namespace: str | None = None,
    pipes_k8s_client: Any | None = None,
    context: Any | None = None,
    user_id: str | None = None,
) -> Any | None:
    """Run a Pipes K8s task on the cluster.

    ``pipes_k8s_client`` is normally the Dagster resource
    instantiated by :class:`PipesK8sClient`. The wrapper injects
    the rate-limit env so the kernel pod debits the right user's
    buckets.
    """
    if pipes_k8s_client is None:
        try:
            from dagster_pipes import PipesK8sClient  # type: ignore[import-not-found]

            pipes_k8s_client = PipesK8sClient()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "PipesK8sClient unavailable (%s); cannot run cloud Pipes task",
                exc,
            )
            return None
    full_env = {
        "HTTPS_PROXY": "http://rl-proxy.aqp-system.svc.cluster.local:8080",
        "HTTP_PROXY": "http://rl-proxy.aqp-system.svc.cluster.local:8080",
        "AQP_USER_ID": user_id or os.environ.get("AQP_USER_ID", "anonymous"),
    }
    if env:
        full_env.update(env)
    try:
        return pipes_k8s_client.run(
            context=context,
            image=image,
            command=command,
            env=full_env,
            namespace=namespace,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cloud_run_with_pipes failed: %s", exc)
        return None


__all__ = ["cloud_run_with_pipes", "local_pipes_context"]
