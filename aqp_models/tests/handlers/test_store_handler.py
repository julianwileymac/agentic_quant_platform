"""StoreHandler local-fs backend test."""
from __future__ import annotations

from pathlib import Path

from aqp_models.handlers import StoreHandler
from aqp_models.handlers.store_handler import _LocalFsBackend


def test_store_handler_local_fs_round_trip(tmp_path: Path) -> None:
    src = tmp_path / "artifact.pkl"
    src.write_bytes(b"\x80\x04N.")  # tiny valid pickle bytes for None

    backend_dir = tmp_path / "store"
    handler = StoreHandler(backend=_LocalFsBackend(base_dir=backend_dir))
    result = handler.invoke(
        source_path=str(src),
        object_key="models/test.pkl",
    )
    assert result.ok, result.error
    target = backend_dir / "models" / "test.pkl"
    assert target.exists()
    assert target.read_bytes() == src.read_bytes()
