"""Lightweight controller for the vLLM service profiles defined in
``docker-compose.yml``.

Two operating modes are supported transparently:

- **Docker Compose** (preferred): ``docker compose --profile <p> up -d <svc>``
  / ``down``. We only operate on services whose Compose ``profiles`` list
  includes the chosen profile, so we never touch unrelated containers.
- **Plain probe**: when Docker isn't available we still answer ``status``
  by hitting the configured ``base_url`` (``/v1/models``) so the UI can
  show whether an externally-managed vLLM is reachable.

A vLLM "profile" is a YAML file under ``configs/llm/`` with at least
``base_url`` and ``served_model_name`` fields. Each profile is mapped to
a Compose service via the ``compose_service`` (defaults to the profile
filename minus extension) and ``compose_profile`` keys (defaults to the
``provider`` value, typically ``vllm``).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aqp.config import settings

logger = logging.getLogger(__name__)


# Configs/llm relative to the package root: <repo>/configs/llm/*.yaml
_CONFIGS_LLM = Path(__file__).resolve().parent.parent.parent / "configs" / "llm"


@dataclass(frozen=True)
class VllmProfile:
    """A loaded ``configs/llm/*.yaml`` preset."""

    name: str
    path: Path
    provider: str
    model: str
    served_model_name: str
    base_url: str
    hf_model_id: str
    compose_profile: str
    compose_service: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "provider": self.provider,
            "model": self.model,
            "served_model_name": self.served_model_name,
            "base_url": self.base_url,
            "hf_model_id": self.hf_model_id,
            "compose_profile": self.compose_profile,
            "compose_service": self.compose_service,
        }


def _load_profile(path: Path) -> VllmProfile | None:
    """Parse a single ``configs/llm/*.yaml`` file into a profile."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("vllm profile %s could not be parsed: %s", path, exc)
        return None
    if str(raw.get("provider") or "").lower() != "vllm":
        return None
    name = path.stem
    served = str(raw.get("served_model_name") or raw.get("model") or "")
    compose_profile = str(raw.get("compose_profile") or "vllm").strip()
    compose_service = str(raw.get("compose_service") or "").strip() or _default_service(name)
    return VllmProfile(
        name=name,
        path=path,
        provider="vllm",
        model=str(raw.get("model") or served or name),
        served_model_name=served or name,
        base_url=str(raw.get("base_url") or "").strip(),
        hf_model_id=str(raw.get("hf_model_id") or ""),
        compose_profile=compose_profile,
        compose_service=compose_service,
        raw=dict(raw),
    )


def _default_service(profile_name: str) -> str:
    """Map ``vllm_fingpt`` -> ``vllm-fingpt`` and ``vllm_nemotron`` -> ``vllm``."""
    slug = profile_name.replace("_", "-")
    if slug in {"vllm-nemotron", "vllm-default"}:
        return "vllm"
    return slug


def list_profiles(root: Path | None = None) -> list[VllmProfile]:
    """Return every ``configs/llm/*.yaml`` file that has ``provider: vllm``."""
    base = root or _CONFIGS_LLM
    if not base.exists():
        return []
    out: list[VllmProfile] = []
    for path in sorted(base.glob("*.yaml")):
        profile = _load_profile(path)
        if profile is not None:
            out.append(profile)
    return out


def get_profile(name: str) -> VllmProfile | None:
    """Look up a profile by ``name`` (filename without extension)."""
    safe = str(name or "").strip()
    if not safe:
        return None
    target = _CONFIGS_LLM / f"{safe}.yaml"
    if target.exists():
        return _load_profile(target)
    for profile in list_profiles():
        if profile.name == safe:
            return profile
    return None


# ---------------------------------------------------------------------------
# Docker Compose integration
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _compose_cmd() -> list[str]:
    """Return the ``docker compose`` CLI invocation."""
    return ["docker", "compose"]


def _run(cmd: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    """Run a command and return the completed process (text mode)."""
    logger.debug("running %s", cmd)
    return subprocess.run(  # noqa: S603 -- argv list, not shell
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def compose_status(service: str) -> dict[str, Any]:
    """Return ``{"running": bool, "state": "...", "raw": "..."}`` for ``service``.

    Uses ``docker compose ps --format json`` so we don't depend on
    ``--status`` flag availability across compose plugin versions.
    """
    if not _docker_available():
        return {"running": False, "state": "no-docker", "raw": ""}

    proc = _run([*_compose_cmd(), "ps", "--format", "json", service], timeout=20.0)
    if proc.returncode != 0:
        return {
            "running": False,
            "state": "compose-error",
            "raw": proc.stderr.strip() or proc.stdout.strip(),
        }

    raw = proc.stdout.strip()
    if not raw:
        return {"running": False, "state": "stopped", "raw": ""}

    import json as _json

    state = "unknown"
    running = False
    try:
        # docker compose may emit either a JSON array or NDJSON.
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            blob = _json.loads(line)
            if isinstance(blob, list):
                if not blob:
                    continue
                blob = blob[0]
            if isinstance(blob, dict):
                state = str(blob.get("State") or blob.get("Status") or "unknown")
                running = state.lower() in {"running", "starting", "healthy"}
                break
    except Exception:  # noqa: BLE001
        return {"running": False, "state": "parse-error", "raw": raw}
    return {"running": running, "state": state, "raw": raw}


def compose_up(profile: VllmProfile, *, timeout: float = 120.0) -> dict[str, Any]:
    """Run ``docker compose --profile <p> up -d <svc>`` for the given profile."""
    if not _docker_available():
        raise RuntimeError("docker CLI not available; install Docker or start vLLM manually")

    cmd = [
        *_compose_cmd(),
        "--profile",
        profile.compose_profile,
        "up",
        "-d",
        profile.compose_service,
    ]
    proc = _run(cmd, timeout=timeout)
    return {
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": " ".join(cmd),
    }


def compose_down(profile: VllmProfile, *, timeout: float = 60.0) -> dict[str, Any]:
    """Stop the Compose service backing ``profile``.

    Uses ``docker compose stop <svc>`` which is non-destructive (the
    container is preserved so a subsequent ``up`` is fast).
    """
    if not _docker_available():
        raise RuntimeError("docker CLI not available")
    cmd = [*_compose_cmd(), "stop", profile.compose_service]
    proc = _run(cmd, timeout=timeout)
    return {
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": " ".join(cmd),
    }


def compose_logs(profile: VllmProfile, *, tail: int = 200) -> str:
    """Return the last ``tail`` lines of the service's container logs."""
    if not _docker_available():
        return ""
    cmd = [*_compose_cmd(), "logs", "--tail", str(int(tail)), profile.compose_service]
    proc = _run(cmd, timeout=30.0)
    return (proc.stdout or proc.stderr or "").strip()


# ---------------------------------------------------------------------------
# HTTP probe
# ---------------------------------------------------------------------------


def probe_endpoint(base_url: str, *, timeout: float = 3.0) -> dict[str, Any]:
    """Probe a vLLM ``/v1/models`` endpoint, returning available model ids."""
    if not base_url:
        return {"online": False, "models": [], "error": "no base_url"}
    target = base_url.rstrip("/")
    if target.endswith("/v1"):
        target = target[: -len("/v1")]
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{target}/v1/models")
            resp.raise_for_status()
            obj = resp.json() or {}
        items = obj.get("data") if isinstance(obj, dict) else []
        return {
            "online": True,
            "models": [str(m.get("id", "")) for m in items if isinstance(m, dict)],
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"online": False, "models": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# Public summaries used by routes
# ---------------------------------------------------------------------------


def summarize_profile(profile: VllmProfile) -> dict[str, Any]:
    """Combine compose status + endpoint probe into a single payload."""
    status = compose_status(profile.compose_service)
    probe = probe_endpoint(profile.base_url)
    return {
        **profile.to_dict(),
        "compose": status,
        "probe": probe,
    }


def serving_summary() -> dict[str, Any]:
    """Snapshot for the UI dashboard."""
    profiles = [summarize_profile(p) for p in list_profiles()]
    active_url = (settings.vllm_base_url or "").strip()
    return {
        "configured_base_url": active_url,
        "docker_available": _docker_available(),
        "profiles": profiles,
    }


__all__ = [
    "VllmProfile",
    "compose_down",
    "compose_logs",
    "compose_status",
    "compose_up",
    "get_profile",
    "list_profiles",
    "probe_endpoint",
    "serving_summary",
    "summarize_profile",
]
