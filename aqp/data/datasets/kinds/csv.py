"""CSV :class:`BaseDataset` (pandas-backed)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aqp.data.datasets.base import BaseDataset


class CSVDataset(BaseDataset):
    kind = "csv"
    writable = True

    def _validate_spec(self) -> None:
        if not str(self._spec.config.get("filepath") or "").strip():
            raise ValueError("CSVDataset requires config.filepath")

    @property
    def filepath(self) -> str:
        return str(self._spec.config["filepath"])

    def _load(self) -> Any:
        import pandas as pd

        load_args = dict(self._spec.config.get("load_args") or {})
        return pd.read_csv(self.filepath, **load_args)

    def _save(self, payload: Any) -> Any:
        import pandas as pd

        save_args = dict(self._spec.config.get("save_args") or {})
        save_args.setdefault("index", False)
        Path(self.filepath).parent.mkdir(parents=True, exist_ok=True)
        if not isinstance(payload, pd.DataFrame):
            payload = pd.DataFrame(payload)
        payload.to_csv(self.filepath, **save_args)
        return self.filepath

    def _exists(self) -> bool:
        return Path(self.filepath).exists()

    def _describe(self) -> dict[str, Any]:
        return {"filepath": self.filepath, "load_mode": "csv"}


__all__ = ["CSVDataset"]
