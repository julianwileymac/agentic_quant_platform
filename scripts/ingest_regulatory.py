"""Director-driven ingest of the four regulatory corpora into Iceberg.

Run from inside the ``aqp-api`` (or ``aqp-worker``) container::

    docker exec aqp-api python -m scripts.ingest_regulatory

Steps performed:

1. Verify the Nemotron Director model is pulled in Ollama
   (``GET /api/tags``); pull it if missing (``POST /api/pull``).
2. Resolve which of ``cfpb``, ``uspto``, ``fda``, ``sec`` actually exist
   under ``--host-root`` (defaults to ``/host-downloads``).
3. For each source, spawn a fresh Python subprocess that runs the full
   discovery → director-plan → materialise → verify → annotate
   pipeline once. Per-source isolation keeps memory pressure bounded.
4. Aggregate the per-source :class:`IngestionReport` JSON payloads,
   print a Markdown summary, and write a JSON audit log to
   ``/warehouse/logs/ingest_<timestamp>.json``.

Use ``--dry-run`` to print the resolved sources without dispatching
any work.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx


DEFAULT_HOST_ROOT = "/host-downloads"
DEFAULT_OLLAMA_BASE = "http://host.docker.internal:11434"
DEFAULT_LOG_DIR = "/warehouse/logs"
DEFAULT_MODEL = "nemotron-3-nano:30b"
REGULATORY_SOURCES = ("cfpb", "uspto", "fda", "sec")
REGULATORY_NAMESPACES = {
    "cfpb": "aqp_cfpb",
    "uspto": "aqp_uspto",
    "fda": "aqp_fda",
    "sec": "aqp_sec",
}


def _stamp() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# Ollama probe / pull
# ---------------------------------------------------------------------------


def ensure_director_model(ollama_base: str, model: str, *, timeout: float = 60.0) -> None:
    """Make sure ``model`` is present in Ollama; pull it if missing."""
    base = ollama_base.rstrip("/")
    print(f"[ollama] probing {base}/api/tags …")
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{base}/api/tags")
            resp.raise_for_status()
            tags = {entry.get("name") for entry in (resp.json().get("models") or [])}
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"[ollama] could not reach {base}: {exc}. Is Ollama running on the host?"
        ) from exc

    if model in tags:
        print(f"[ollama] {model} already pulled — skipping pull")
        return
    if any((model.split(":", 1)[0]) == (t.split(":", 1)[0]) for t in tags if t):
        print(f"[ollama] tag prefix for {model} already present in registry")
        return

    print(f"[ollama] pulling {model} (this can take a while for 30B weights) …")
    payload = {"model": model, "stream": True}
    try:
        with httpx.Client(timeout=None) as client:
            with client.stream(
                "POST", f"{base}/api/pull", json=payload, headers={"Accept": "application/x-ndjson"}
            ) as resp:
                resp.raise_for_status()
                for raw_line in resp.iter_lines():
                    line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", "replace")
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    status = msg.get("status") or ""
                    if msg.get("error"):
                        raise SystemExit(f"[ollama] pull failed: {msg['error']}")
                    completed = msg.get("completed") or 0
                    total = msg.get("total") or 0
                    if total:
                        print(
                            f"[ollama] {status} ({completed/(1024*1024):.1f}/"
                            f"{total/(1024*1024):.1f} MB)",
                            flush=True,
                        )
                    else:
                        print(f"[ollama] {status}", flush=True)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"[ollama] pull failed: {exc}") from exc

    print(f"[ollama] pulled {model}")


# ---------------------------------------------------------------------------
# Per-source subprocess runner
# ---------------------------------------------------------------------------


def run_one_source(
    *,
    src: str,
    path: str,
    namespace: str,
    allowed_namespaces: list[str],
    annotate: bool,
    director_enabled: bool,
    max_rows: int | None,
    max_files: int | None,
    chunk_rows: int,
    log_dir: str,
) -> dict[str, Any]:
    """Spawn a fresh ``python -m scripts._run_one_source`` for ``src``.

    Capturing per-source stdout into a sibling log file gives us a
    reusable progress trail when something fails. The aggregated
    :class:`IngestionReport` JSON is read back from disk and returned
    so the parent can build the final markdown summary.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    report_path = Path(log_dir) / f"ingest_{src}_{stamp}.json"
    progress_path = Path(log_dir) / f"ingest_{src}_{stamp}.log"

    cmd = [
        sys.executable,
        "-m",
        "scripts._run_one_source",
        "--path",
        path,
        "--namespace",
        namespace,
        "--report",
        str(report_path),
        "--chunk-rows",
        str(int(chunk_rows)),
    ]
    if annotate:
        cmd.append("--annotate")
    if not director_enabled:
        cmd.append("--no-director")
    if max_rows is not None:
        cmd.extend(["--max-rows", str(int(max_rows))])
    if max_files is not None:
        cmd.extend(["--max-files", str(int(max_files))])
    for ns in allowed_namespaces:
        cmd.extend(["--allowed-namespace", ns])

    print(f"\n[runner] {src} -> {namespace}: spawning subprocess")
    print(f"[runner] cmd = {' '.join(cmd)}")
    print(f"[runner] streaming progress to {progress_path}")

    with progress_path.open("w", encoding="utf-8") as out_fh:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip("\n")
                print(f"[{src}] {line}", flush=True)
                out_fh.write(line + "\n")
                out_fh.flush()
        except KeyboardInterrupt:
            proc.terminate()
            raise
        rc = proc.wait()

    payload: dict[str, Any] = {
        "source": src,
        "exit_code": int(rc),
        "report_path": str(report_path),
        "progress_path": str(progress_path),
    }
    if report_path.exists():
        try:
            payload["report"] = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            payload["report_parse_error"] = str(exc)
    return payload


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def render_markdown(per_source: list[dict[str, Any]]) -> str:
    lines = [
        "| Source | Namespace | Discovered | Tables | Rows | Errors | Subprocess RC |",
        "| ------ | --------- | ----------:| -----: | ---: | -----: | ------------: |",
    ]
    for entry in per_source:
        report = entry.get("report") or {}
        src = entry.get("source") or "-"
        ns = report.get("namespace") or "-"
        discovered = report.get("datasets_discovered") or 0
        tables = report.get("tables") or []
        rows = sum(int(t.get("rows_written") or 0) for t in tables)
        errors = report.get("errors") or []
        if not report and entry.get("report_parse_error"):
            errors = [entry["report_parse_error"]]
        rc = entry.get("exit_code")
        lines.append(
            f"| {src} | {ns} | {discovered} | {len(tables)} | {rows:,} | {len(errors)} | {rc} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_audit_log(log_dir: str, payload: dict[str, Any]) -> str:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    out = Path(log_dir) / f"ingest_{_stamp()}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources",
        default=",".join(REGULATORY_SOURCES),
        help="Comma-separated subset of cfpb,uspto,fda,sec",
    )
    parser.add_argument("--host-root", default=DEFAULT_HOST_ROOT)
    parser.add_argument(
        "--ollama-base",
        default=os.environ.get("AQP_OLLAMA_HOST", DEFAULT_OLLAMA_BASE),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("AQP_LLM_DIRECTOR_MODEL", DEFAULT_MODEL),
        help="Ollama tag for the Director model",
    )
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--chunk-rows", type=int, default=10_000)
    parser.add_argument(
        "--no-annotate",
        action="store_true",
        help="Skip the per-table LLM annotation pass.",
    )
    parser.add_argument(
        "--no-director",
        action="store_true",
        help="Run with the deterministic identity plan (no LLM planner).",
    )
    parser.add_argument(
        "--skip-pull",
        action="store_true",
        help="Skip the Ollama probe/pull step.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve sources and print the plan preview but do not dispatch.",
    )
    args = parser.parse_args()

    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in sources if s not in REGULATORY_SOURCES]
    if unknown:
        raise SystemExit(f"unknown sources: {unknown}; allowed: {REGULATORY_SOURCES}")

    host_root = Path(args.host_root).expanduser()
    if not host_root.exists():
        raise SystemExit(f"host_root does not exist: {host_root}")
    resolved: dict[str, Path] = {}
    missing: list[str] = []
    for src in sources:
        candidate = host_root / src
        if candidate.exists():
            resolved[src] = candidate
        else:
            missing.append(str(candidate))
    if missing:
        print(f"[pre] missing under {host_root}: {missing}")
    if not resolved:
        raise SystemExit("no regulatory subdirs found; aborting")

    print("[pre] resolved sources:")
    for src, p in resolved.items():
        print(f"       - {src}: {p} -> namespace={REGULATORY_NAMESPACES[src]}")

    if not args.skip_pull and not args.no_director:
        ensure_director_model(args.ollama_base, args.model)

    if args.dry_run:
        print("[dry-run] not dispatching ingest")
        return 0

    allowed_namespaces = sorted(REGULATORY_NAMESPACES[s] for s in resolved)

    per_source: list[dict[str, Any]] = []
    started = _stamp()
    for src, path in resolved.items():
        ns = REGULATORY_NAMESPACES[src]
        try:
            payload = run_one_source(
                src=src,
                path=str(path),
                namespace=ns,
                allowed_namespaces=allowed_namespaces,
                annotate=not args.no_annotate,
                director_enabled=not args.no_director,
                max_rows=args.max_rows,
                max_files=args.max_files,
                chunk_rows=args.chunk_rows,
                log_dir=args.log_dir,
            )
        except KeyboardInterrupt:
            print(f"[runner] interrupted during {src}")
            raise
        except Exception as exc:  # noqa: BLE001
            payload = {
                "source": src,
                "error": str(exc),
                "exit_code": -1,
            }
        per_source.append(payload)

    print()
    print(render_markdown(per_source))

    audit = {
        "started": started,
        "finished": _stamp(),
        "sources": list(resolved.keys()),
        "host_root": str(host_root),
        "model": args.model,
        "director_enabled": not args.no_director,
        "annotate": not args.no_annotate,
        "max_rows_per_dataset": args.max_rows,
        "max_files_per_dataset": args.max_files,
        "chunk_rows": args.chunk_rows,
        "per_source": per_source,
    }
    log_path = write_audit_log(args.log_dir, audit)
    print(f"[audit] wrote {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
