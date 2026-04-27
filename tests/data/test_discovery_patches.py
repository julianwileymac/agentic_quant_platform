"""Discovery patches: SEC subdirectory disambiguation, USPTO-style XML
inventory, and FDA-style ``(N)`` browser-duplicate suppression.

These tests exercise :func:`aqp.data.pipelines.discovery.discover_datasets`
on synthetic filesystem trees so they don't depend on the real CFPB / FDA
/ SEC / USPTO downloads.
"""
from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path


def _write_csv(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def _write_zip_with_csv(path: Path, member_name: str, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = header + "\n" + "\n".join(rows) + "\n"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, body)


def _write_zip_with_xml(path: Path, member_name: str, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, payload)


def test_sec_subdir_disambiguation_keeps_families_apart(tmp_path: Path) -> None:
    """``2024q1`` files in two SEC subdirs must NOT collapse into one family."""
    from aqp.data.pipelines.discovery import discover_datasets

    # Mimic the SEC release layout: two sibling subdirs, identical-looking
    # leaf names that would collide on the bare ``2024q1`` family key.
    fs_root = tmp_path / "sec"
    _write_zip_with_csv(
        fs_root / "financial_statement_data_sets" / "2024q1.zip",
        "num.txt",
        "adsh\tval\tperiod",
        ["a\t1\t2024-03-31"],
    )
    _write_zip_with_csv(
        fs_root / "business_development_companies_data_sets" / "2024q1_bdc.zip",
        "bdc.tsv",
        "filer\ttotal_assets",
        ["X\t100"],
    )

    datasets = discover_datasets(fs_root)
    families = {d.family for d in datasets if d.family != "__assets__"}

    # Both subdirs must surface their family with a subdir-prefixed key.
    fs_family = next((f for f in families if "financial_statement" in f), None)
    bdc_family = next((f for f in families if "business_development" in f), None)
    assert fs_family is not None, families
    assert bdc_family is not None, families
    assert fs_family != bdc_family


def test_uspto_xml_routes_to_assets_with_notes(tmp_path: Path) -> None:
    """USPTO ipa*.zip whose only payload is XML lands under ``__assets__``."""
    from aqp.data.pipelines.discovery import discover_datasets

    fs_root = tmp_path / "uspto"
    _write_zip_with_xml(
        fs_root / "ipa260101.zip",
        "ipa260101.xml",
        "<patent-application></patent-application>",
    )

    datasets = discover_datasets(fs_root)
    by_family = {d.family: d for d in datasets}

    assert "__assets__" in by_family, list(by_family)
    assets = by_family["__assets__"]
    assert any("XML" in note for note in assets.notes), assets.notes
    assert assets.inventory_extra, "inventory_extra should list the xml-bearing zip"

    # The xml zip must NOT also produce a tabular family.
    tabular_families = [f for f in by_family if f != "__assets__"]
    assert tabular_families == [], tabular_families


def test_fda_browser_duplicate_suffix_collapses(tmp_path: Path) -> None:
    """``foo (1).zip`` collapses with ``foo.zip`` and the older copy is dropped."""
    from aqp.data.pipelines.discovery import discover_datasets

    fs_root = tmp_path / "fda"
    original = fs_root / "device-event-0001-of-0007.json.zip"
    duplicate = fs_root / "device-event-0001-of-0007.json (1).zip"
    _write_zip_with_csv(
        original,
        "device-event-0001-of-0007.json",
        "event_id,outcome",
        ["E1,ok", "E2,fail"],
    )
    _write_zip_with_csv(
        duplicate,
        "device-event-0001-of-0007.json",
        "event_id,outcome",
        ["E1,ok", "E2,fail", "E3,ok"],
    )

    # Make the ``(1)`` copy strictly newer so it should be the survivor.
    now = time.time()
    os.utime(original, (now - 60, now - 60))
    os.utime(duplicate, (now, now))

    datasets = discover_datasets(fs_root)
    by_family = {d.family: d for d in datasets if d.family != "__assets__"}
    assert by_family, list(d.family for d in datasets)
    family = next(iter(by_family.values()))

    kept_paths = {Path(m.path).name for m in family.members}
    assert kept_paths == {"device-event-0001-of-0007.json (1).zip"}, kept_paths

    assert any("duplicate" in note.lower() for note in family.notes), family.notes
    suppressed = [
        entry for entry in family.inventory_extra
        if entry.get("reason") == "duplicate-suffix-suppressed"
    ]
    assert suppressed, family.inventory_extra
