"""Round-trip tests for ``aqp.visualization.superset_bundle``."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from aqp.visualization.superset_bundle import read_bundle_dir, write_bundle_dir


def _build_zip(files: dict[str, bytes], *, prefix: str = "aqp_bundle/") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for relative, body in files.items():
            zf.writestr(f"{prefix}{relative}", body)
    return buffer.getvalue()


def test_write_bundle_dir_strips_top_level_prefix(tmp_path: Path) -> None:
    zip_bytes = _build_zip(
        {
            "metadata.yaml": b"version: 1.0.0\n",
            "databases/aqp.yaml": b"name: AQP\n",
            "datasets/aqp/sp500.yaml": b"table: sp500\n",
            "charts/aqp_close.yaml": b"slice_name: AQP Close\n",
            "dashboards/aqp.yaml": b"slug: aqp\n",
        }
    )

    target = tmp_path / "extracted"
    write_bundle_dir(zip_bytes, target)

    assert (target / "metadata.yaml").read_text() == "version: 1.0.0\n"
    assert (target / "databases" / "aqp.yaml").read_text() == "name: AQP\n"
    assert (target / "datasets" / "aqp" / "sp500.yaml").exists()
    assert (target / "charts" / "aqp_close.yaml").exists()
    assert (target / "dashboards" / "aqp.yaml").exists()


def test_read_bundle_dir_round_trips_through_zip(tmp_path: Path) -> None:
    source = tmp_path / "bundle"
    source.mkdir()
    (source / "metadata.yaml").write_text("version: 1.0.0\n")
    (source / "databases").mkdir()
    (source / "databases" / "aqp.yaml").write_text("name: AQP\n")
    (source / "dashboards").mkdir()
    (source / "dashboards" / "aqp.yaml").write_text("slug: aqp\n")

    zip_bytes = read_bundle_dir(source, archive_name="aqp_bundle")

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = sorted(zf.namelist())
    assert names == [
        "aqp_bundle/dashboards/aqp.yaml",
        "aqp_bundle/databases/aqp.yaml",
        "aqp_bundle/metadata.yaml",
    ]


def test_read_bundle_dir_raises_when_metadata_missing(tmp_path: Path) -> None:
    incomplete = tmp_path / "bundle"
    incomplete.mkdir()
    (incomplete / "databases").mkdir()
    (incomplete / "databases" / "aqp.yaml").write_text("name: AQP\n")

    try:
        read_bundle_dir(incomplete)
    except FileNotFoundError as exc:
        assert "metadata.yaml" in str(exc)
    else:  # pragma: no cover - asserts above must trigger
        raise AssertionError("read_bundle_dir should reject incomplete bundles")
