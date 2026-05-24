"""Snippet safety + content-hash tests (no DB)."""
from __future__ import annotations

from aqp.lab.snippets import compute_snippet_hash, safety_check


def test_safety_check_accepts_safe_python() -> None:
    assert safety_check("import pandas as pd\ndf = pd.DataFrame()", "python") is True


def test_safety_check_rejects_os_system() -> None:
    assert safety_check("import os\nos.system('echo pwn')", "python") is False


def test_safety_check_rejects_subprocess_import() -> None:
    assert safety_check("import subprocess", "python") is False


def test_safety_check_skips_for_sql() -> None:
    # SQL snippets pass the AST guard automatically — the DuckDB
    # tool has its own policy check.
    assert safety_check("SELECT * FROM bars LIMIT 10", "sql") is True


def test_content_hash_is_stable_for_equivalent_source() -> None:
    h1 = compute_snippet_hash("x = 1\n", "python")
    h2 = compute_snippet_hash("x = 1", "python")  # trailing newline stripped
    assert h1 == h2


def test_content_hash_differs_across_languages() -> None:
    h_py = compute_snippet_hash("x = 1", "python")
    h_sql = compute_snippet_hash("x = 1", "sql")
    assert h_py != h_sql
