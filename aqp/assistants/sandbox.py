"""Guarded assistant sandbox abstraction.

Default policy is **blocked-by-default**:

- :meth:`AssistantSandbox.validate_command` rejects shell payloads
  matching the deny list (``rm -rf /``, fork-bombs, ``curl | sh``,
  reverse shells over ``nc`` / ``socat``, …).
- :meth:`AssistantSandbox.resolve_path` rejects path traversal and
  any reference to credential / SSH / cloud-config segments.
- :meth:`AssistantSandbox.execute` returns a structured policy
  refusal unless ``settings.assistant_sandbox_backend`` is set to
  something other than ``"blocked"``. There is no path that lets an
  LLM-generated command land on the host without an explicit
  operator opt-in.

The sandbox NEVER imports a Docker / microVM client until the
operator flips the backend to one of those values. That keeps cold
installs (no Docker daemon) booting cleanly.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from aqp.config import settings

logger = logging.getLogger(__name__)


_BLOCKED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\s+-rf\s+[/~]"),
    re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;:"),
    re.compile(r"\b(?:curl|wget)\b.+\|\s*(?:sh|bash)"),
    re.compile(r"\b(?:nc|netcat|socat)\b.+(?:\s-e\b|/bin/sh|/bin/bash)"),
    re.compile(r"\bsudo\b\s+\S+", re.IGNORECASE),
    re.compile(r"\bdocker\s+(?:run|exec|cp)\b"),
    re.compile(r"\bkubectl\s+(?:exec|cp|delete)\b"),
    re.compile(r"/var/run/docker\.sock"),
    re.compile(r"\bchmod\s+(?:777|666|\+s)\b"),
)

_SENSITIVE_SEGMENTS = frozenset(
    {
        ".env",
        ".envrc",
        ".ssh",
        ".aws",
        ".azure",
        ".gcp",
        ".kube",
        "id_rsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials",
        "auth_token",
        ".docker",
    }
)

_BLOCKED_BACKENDS = frozenset({"blocked", ""})


@dataclass
class SandboxExecutionResult:
    """Structured outcome of a sandbox command attempt."""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    blocked: bool = False
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "blocked": self.blocked,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


class SandboxPolicyError(PermissionError):
    """Raised when a command/path violates sandbox policy."""


class AssistantSandbox:
    """Policy-first sandbox boundary.

    Validation happens BEFORE any execution attempt so policy denials
    are visible in the timeline even when no execution backend is
    configured.
    """

    def __init__(
        self,
        session_id: str,
        *,
        workspace_root: Path | None = None,
        backend: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.workspace_root = Path(
            workspace_root
            or (Path(settings.data_dir) / "assistant_sandbox" / session_id)
        ).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.backend = (
            backend
            if backend is not None
            else getattr(settings, "assistant_sandbox_backend", "blocked")
        )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    def validate_command(self, command: str) -> None:
        """Raise :class:`SandboxPolicyError` when ``command`` is denied."""
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(command):
                raise SandboxPolicyError(
                    f"blocked command pattern: {pattern.pattern}"
                )

    def validate_command_set(
        self, commands: Iterable[str]
    ) -> SandboxExecutionResult:
        """Batch-validate every command and surface every violation.

        Returns a single :class:`SandboxExecutionResult` whose
        ``metadata['violations']`` carries the per-command diagnostics
        the UI uses to render an explicit (non-prompt-injectable)
        permission denial. ``ok=False`` + ``blocked=True`` when any
        command violates policy; ``ok=True`` + ``blocked=False`` when
        every command is allowed by the validator (execution still
        depends on :meth:`execute`).
        """
        violations: list[dict[str, Any]] = []
        for cmd in commands:
            try:
                self.validate_command(cmd)
            except SandboxPolicyError as exc:
                violations.append({"command": cmd, "reason": str(exc)})
        if violations:
            return SandboxExecutionResult(
                ok=False,
                blocked=True,
                reason=f"blocked {len(violations)} command(s) by policy",
                metadata={
                    "violations": violations,
                    "workspace_root": str(self.workspace_root),
                    "backend": self.backend,
                },
            )
        return SandboxExecutionResult(
            ok=True,
            blocked=False,
            reason=None,
            metadata={
                "violations": [],
                "workspace_root": str(self.workspace_root),
                "backend": self.backend,
            },
        )

    def resolve_path(self, path: str | Path) -> Path:
        """Resolve ``path`` inside the workspace, rejecting traversal + secrets."""
        candidate = (self.workspace_root / path).resolve()
        if (
            self.workspace_root not in candidate.parents
            and candidate != self.workspace_root
        ):
            raise SandboxPolicyError("path escapes assistant sandbox workspace")
        lowered = {part.lower() for part in candidate.parts}
        if lowered & _SENSITIVE_SEGMENTS:
            raise SandboxPolicyError(
                "path references sensitive credentials or secret material"
            )
        return candidate

    # ------------------------------------------------------------------
    # Execution gate
    # ------------------------------------------------------------------

    def execute(self, command: str) -> SandboxExecutionResult:
        """Validate then attempt execution.

        With ``backend="blocked"`` (the default) the method NEVER
        reaches a host or container — it returns a structured
        refusal that the UI can render as an explicit permission
        denial.

        With ``backend="docker"`` / ``"microvm"`` a future build will
        plumb in the matching adapter; for now those backends still
        return a refusal so any premature flip stays safe.
        """
        try:
            self.validate_command(command)
        except SandboxPolicyError as exc:
            return SandboxExecutionResult(
                ok=False,
                blocked=True,
                reason=str(exc),
                metadata={
                    "workspace_root": str(self.workspace_root),
                    "backend": self.backend,
                },
            )

        if self.backend in _BLOCKED_BACKENDS:
            return SandboxExecutionResult(
                ok=False,
                blocked=True,
                reason=(
                    "sandbox execution backend not configured; set "
                    "AQP_ASSISTANT_SANDBOX_BACKEND=docker (or microvm) "
                    "and ship the matching adapter before generated "
                    "code can run"
                ),
                metadata={
                    "workspace_root": str(self.workspace_root),
                    "backend": self.backend,
                },
            )

        # Future hook: dispatch to a registered backend adapter (docker
        # SDK / microVM). Until that adapter ships we keep the same
        # structured refusal so a misconfigured flag never silently
        # executes generated code.
        return SandboxExecutionResult(
            ok=False,
            blocked=True,
            reason=(
                f"sandbox backend {self.backend!r} declared but not yet "
                "implemented; refusing to execute"
            ),
            metadata={
                "workspace_root": str(self.workspace_root),
                "backend": self.backend,
            },
        )


__all__ = [
    "AssistantSandbox",
    "SandboxExecutionResult",
    "SandboxPolicyError",
]
