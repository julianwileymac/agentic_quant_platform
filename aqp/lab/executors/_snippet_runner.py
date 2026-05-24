"""Unified snippet runner — Tier 1 (in-process) + Tier 2 (gVisor / Docker).

Phase 4 — the snippet runner picks the execution sandbox based on
``settings.aqp_lab_sandbox_runtime``:

- ``'none'`` (default) — Tier 1 only; Tier 2 returns a structured
  error so the operator sees the gating clearly.
- ``'docker'`` — Docker exec via the Docker Python SDK (no extra
  isolation beyond container boundaries).
- ``'gvisor'`` — Docker exec with the ``runsc`` runtime (gVisor
  user-mode kernel; the recommended production posture).

Tier 1 always uses the in-process :class:`EdaKernel`; Tier 2 spawns
a short-lived container with the snippet's pinned image (from
``settings.aqp_lab_executor_images``) and pipes the source over
stdin / receives the result over stdout JSON.

The runner ALWAYS re-runs the strict AST safety check before
dispatch — the static guard is defence in depth, not a security
boundary, but it catches accidents fast and makes the threat model
explicit. Container image digests are signed into
``LabRun.metrics.snippet_image_digest`` so a "Reproduce" replay
refuses if the digest no longer exists in the registry.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from aqp.config import settings
from aqp.lab.executors._types import NodeContext, NodeResult
from aqp.lab.snippets import safety_check

logger = logging.getLogger(__name__)


@dataclass
class SnippetRunResult:
    status: str  # done | error
    stdout: str = ""
    stderr: str = ""
    repr_value: str | None = None
    error: str | None = None
    duration_ms: float = 0.0
    image_digest: str | None = None
    sandbox_runtime: str = "tier1"


def run_snippet(
    *,
    source: str,
    language: str = "python",
    tier: str = "tier1",
    executor_image_alias: str | None = None,
    inputs: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> SnippetRunResult:
    """Run a user snippet through the requested sandbox tier.

    ``executor_image_alias`` keys into ``settings.aqp_lab_executor_images``
    so the same alias used in the registry surfaces in the run
    ledger as ``snippet_image_digest``.
    """
    started = time.perf_counter()
    if language not in {"python", "sql"}:
        return SnippetRunResult(
            status="error",
            error=f"unknown snippet language {language!r}",
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
    if language == "python" and not safety_check(source, "python"):
        return SnippetRunResult(
            status="error",
            error="snippet failed AST safety check",
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
    if tier == "tier1":
        return _run_tier1(source=source, language=language, inputs=inputs or {}, started=started)
    if tier == "tier2":
        return _run_tier2(
            source=source,
            language=language,
            inputs=inputs or {},
            executor_image_alias=executor_image_alias,
            timeout_seconds=timeout_seconds,
            started=started,
        )
    return SnippetRunResult(
        status="error",
        error=f"unknown snippet tier {tier!r}; valid: tier1, tier2",
        duration_ms=(time.perf_counter() - started) * 1000.0,
    )


# ---------------------------------------------------------------------------
# Tier 1 — in-process EdaKernel
# ---------------------------------------------------------------------------


def _run_tier1(
    *,
    source: str,
    language: str,
    inputs: dict[str, Any],
    started: float,
) -> SnippetRunResult:
    if language == "sql":
        return SnippetRunResult(
            status="error",
            error="SQL snippets must run through the snippet.sql executor (Tier 1)",
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
    from aqp.lab.eda.kernel import EdaKernel

    kernel = EdaKernel(session_id="snippet_runner-tier1")
    kernel._namespace["_inputs"] = inputs  # noqa: SLF001
    for name, value in inputs.items():
        if name not in {"pd", "np", "db", "scan", "iceberg", "duckdb"}:
            kernel._namespace[name] = value  # noqa: SLF001
    outcome = kernel.execute_cell("snippet", source)
    return SnippetRunResult(
        status=outcome.status,
        stdout=outcome.stdout or "",
        stderr=outcome.stderr or "",
        repr_value=outcome.repr_value,
        error=outcome.error,
        duration_ms=(time.perf_counter() - started) * 1000.0,
        sandbox_runtime="tier1",
    )


# ---------------------------------------------------------------------------
# Tier 2 — gVisor / Docker
# ---------------------------------------------------------------------------


def _run_tier2(
    *,
    source: str,
    language: str,
    inputs: dict[str, Any],
    executor_image_alias: str | None,
    timeout_seconds: float | None,
    started: float,
) -> SnippetRunResult:
    runtime = (getattr(settings, "aqp_lab_sandbox_runtime", "none") or "none").lower()
    if runtime not in {"docker", "gvisor"}:
        return SnippetRunResult(
            status="error",
            error=(
                f"Tier-2 sandbox not configured (settings.aqp_lab_sandbox_runtime={runtime!r}). "
                "Set to 'docker' or 'gvisor' in your AQP settings to enable Tier 2 dispatch."
            ),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            sandbox_runtime="tier2",
        )

    image_map: dict[str, str] = dict(
        getattr(settings, "aqp_lab_executor_images", {}) or {}
    )
    alias = executor_image_alias or "default"
    image_digest = image_map.get(alias)
    if not image_digest:
        return SnippetRunResult(
            status="error",
            error=(
                f"no image registered for alias {alias!r}; populate "
                "settings.aqp_lab_executor_images so the Tier-2 runner has "
                "a pinned digest to pull."
            ),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            sandbox_runtime=runtime,
        )

    try:
        import docker  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return SnippetRunResult(
            status="error",
            error=f"docker python SDK not installed: {exc}",
            duration_ms=(time.perf_counter() - started) * 1000.0,
            sandbox_runtime=runtime,
        )

    timeout = float(timeout_seconds or getattr(settings, "aqp_lab_snippet_timeout_seconds", 300))
    payload = {
        "language": language,
        "source": source,
        "inputs": inputs,
    }
    client = docker.from_env()
    try:
        container = client.containers.create(
            image=image_digest,
            command=["python", "-m", "aqp.lab.executors._snippet_entrypoint"],
            runtime="runsc" if runtime == "gvisor" else None,
            stdin_open=True,
            network_disabled=True,
            mem_limit="2g",
            cpu_quota=200_000,
            cpu_period=100_000,
            detach=True,
        )
    except Exception as exc:  # noqa: BLE001
        return SnippetRunResult(
            status="error",
            error=f"snippet container create failed: {exc}",
            duration_ms=(time.perf_counter() - started) * 1000.0,
            sandbox_runtime=runtime,
            image_digest=image_digest,
        )

    try:
        sock = container.attach_socket(params={"stdin": 1, "stream": 1})
        try:
            sock._sock.sendall(json.dumps(payload).encode("utf-8") + b"\n")  # type: ignore[attr-defined]
        finally:
            try:
                sock.close()
            except Exception:  # noqa: BLE001
                pass
        container.start()
        try:
            container.wait(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            container.kill()
            return SnippetRunResult(
                status="error",
                error=f"snippet container timed out / wait failed: {exc}",
                duration_ms=(time.perf_counter() - started) * 1000.0,
                sandbox_runtime=runtime,
                image_digest=image_digest,
            )
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
    finally:
        try:
            container.remove(force=True)
        except Exception:  # noqa: BLE001
            pass

    # Parse the entrypoint's JSON reply off the last line of stdout —
    # the entrypoint is responsible for writing exactly one JSON line.
    repr_value: str | None = None
    error: str | None = None
    status = "done"
    try:
        last_line = next((ln for ln in reversed(stdout.splitlines()) if ln.strip()), "")
        if last_line.strip().startswith("{"):
            reply = json.loads(last_line)
            status = str(reply.get("status") or "done")
            repr_value = reply.get("repr")
            error = reply.get("error")
            stdout = "\n".join(stdout.splitlines()[:-1])
    except Exception as exc:  # noqa: BLE001
        logger.debug("snippet tier-2 reply parse failed: %s", exc)

    return SnippetRunResult(
        status=status,
        stdout=stdout,
        stderr=stderr,
        repr_value=repr_value,
        error=error,
        duration_ms=(time.perf_counter() - started) * 1000.0,
        image_digest=image_digest,
        sandbox_runtime=runtime,
    )


# ---------------------------------------------------------------------------
# Convenience wrapper for executor modules
# ---------------------------------------------------------------------------


def run_snippet_from_node(
    node: Any,
    ctx: NodeContext,
    *,
    source: str,
    language: str = "python",
) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    tier = str(params.get("tier") or "tier1").lower()
    result = run_snippet(
        source=source,
        language=language,
        tier=tier,
        executor_image_alias=str(params.get("executor_image_alias") or "default"),
        inputs=dict(ctx.upstream or {}),
        timeout_seconds=params.get("timeout_seconds"),
    )
    metrics = {
        "duration_ms": float(round(result.duration_ms, 3)),
        "sandbox_runtime": result.sandbox_runtime,
    }
    locator: dict[str, Any] = {
        "kind": "snippet_inline",
        "tier": tier,
        "sandbox_runtime": result.sandbox_runtime,
        "image_digest": result.image_digest,
        "value_repr": result.repr_value or "",
        "stdout": result.stdout,
        "stderr": result.stderr,
        "node_id": ctx.node_id,
    }
    if result.status == "error":
        return NodeResult(
            status="error",
            error=result.error or "snippet returned error",
            metrics=metrics,
            log_label=f"snippet.{language}:{tier}:error",
        )
    return NodeResult(
        status="done",
        output_locator=locator,
        metrics=metrics,
        log_label=f"snippet.{language}:{tier}:done",
    )


__all__ = [
    "SnippetRunResult",
    "run_snippet",
    "run_snippet_from_node",
]
