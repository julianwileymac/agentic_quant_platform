"""Save / load round-trip + checksum sidecar tests."""
from __future__ import annotations

import hashlib
from pathlib import Path

from aqp_models.handlers import LoadHandler, SaveHandler


def test_pickle_save_writes_artifact_and_sidecar(tmp_path: Path) -> None:
    handler = SaveHandler()
    payload = {"weights": [1.0, 2.0, 3.0]}

    result = handler.invoke(model=payload, dest_dir=str(tmp_path), name="demo")
    assert result.ok, result.error
    target = Path(result.data["path"])  # type: ignore[index]
    assert target.exists()
    sidecar = target.with_suffix(target.suffix + ".sha256")
    assert sidecar.exists()

    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    assert expected == result.metadata["sha256"]


def test_load_handler_rejects_checksum_mismatch(tmp_path: Path) -> None:
    handler = SaveHandler()
    result = handler.invoke(
        model={"hello": "world"}, dest_dir=str(tmp_path), name="demo"
    )
    artifact = Path(result.data["path"])  # type: ignore[index]
    real_sha = result.metadata["sha256"]

    loader = LoadHandler()
    # Pass an obviously-wrong expected hash.
    bad = loader.invoke(
        artifact_path=str(artifact),
        expected_sha256="0" * 64,
        format="pickle",
    )
    assert bad.ok is False
    assert "checksum mismatch" in (bad.error or "")

    # Pass the right hash to confirm the happy path round-trips.
    good = loader.invoke(
        artifact_path=str(artifact),
        expected_sha256=real_sha,
        format="pickle",
    )
    assert good.ok, good.error
    assert good.data == {"hello": "world"}
