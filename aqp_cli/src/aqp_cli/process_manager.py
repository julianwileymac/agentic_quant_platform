"""Helpers for managing long-running local dev processes."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def clear_state(path: Path) -> None:
    if path.exists():
        path.unlink()


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        tasklist = os.path.join(
            os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "System32",
            "tasklist.exe",
        )
        check = subprocess.run(  # noqa: S603
            [tasklist, "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        out = (check.stdout or "").strip()
        return out != "" and "No tasks are running" not in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start_background_process(
    *,
    state_file: Path,
    log_file: Path,
    command: list[str],
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Start a process and persist pid/metadata to a state file."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("ab") as log_handle:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            if sys.platform.startswith("win")
            else 0,
        )
    payload = {
        "pid": int(process.pid),
        "command": command,
        "cwd": str(cwd) if cwd else "",
        "log_file": str(log_file),
        "started_at": _utc_now(),
    }
    write_state(state_file, payload)
    return payload


def stop_background_process(state_file: Path) -> dict[str, Any]:
    """Stop the process referenced in a state file."""
    state = read_state(state_file)
    pid = int(state.get("pid") or 0)
    if pid <= 0:
        return {"stopped": False, "reason": "no_pid"}
    if not is_pid_running(pid):
        clear_state(state_file)
        return {"stopped": False, "reason": "not_running", "pid": pid}

    if sys.platform.startswith("win"):
        taskkill = os.path.join(
            os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "System32",
            "taskkill.exe",
        )
        subprocess.run(  # noqa: S603
            [taskkill, "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    else:
        with suppress(OSError):
            os.kill(pid, signal.SIGTERM)
    clear_state(state_file)
    return {"stopped": True, "pid": pid}


def tail_file(path: Path, *, lines: int = 200) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if lines <= 0:
        return "\n".join(data)
    return "\n".join(data[-lines:])
