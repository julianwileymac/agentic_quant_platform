"""Alpha360 feature factory — 60-step OHLCV panel (native port).

For each field in ``{CLOSE, OPEN, HIGH, LOW, VWAP, VOLUME}`` we emit 60
lagged values normalised by the last close (or last volume). That yields
6 × 60 = 360 features per ``(datetime, vt_symbol)``, matching qlib's
Alpha360 spec.

Reference: ``inspiration/qlib-main/qlib/contrib/data/loader.py``
(``Alpha360DL.get_feature_config``).
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.features.alpha158 import _default_infer_processors, _default_learn_processors
from aqp.ml.handler import DataHandlerLP
from aqp.ml.loader import AQPDataLoader


class Alpha360DL:
    N_STEPS = 60

    @staticmethod
    def get_feature_config(n_steps: int = 60) -> tuple[list[str], list[str]]:
        fields: list[str] = []
        names: list[str] = []
        for field in ("CLOSE", "OPEN", "HIGH", "LOW", "VWAP"):
            for k in range(n_steps - 1, -1, -1):
                if k == 0:
                    fields.append(f"${field.lower()} / $close")
                else:
                    fields.append(f"Ref(${field.lower()}, {k}) / $close")
                names.append(f"{field}{n_steps - 1 - k}")
        for k in range(n_steps - 1, -1, -1):
            if k == 0:
                fields.append("$volume / ($volume + 1e-12)")
            else:
                fields.append(f"Ref($volume, {k}) / ($volume + 1e-12)")
            names.append(f"VOLUME{n_steps - 1 - k}")
        return fields, names

    @staticmethod
    def get_label_config() -> tuple[list[str], list[str]]:
        return (["Ref($close, -2) / Ref($close, -1) - 1"], ["LABEL0"])


@register("Alpha360")
class Alpha360(DataHandlerLP):
    """Alpha360 handler — 60-bar OHLCV panel per sample."""

    def __init__(
        self,
        instruments: list[str] | None = None,
        start_time: str | Any = None,
        end_time: str | Any = None,
        fit_start_time: str | Any = None,
        fit_end_time: str | Any = None,
        n_steps: int = 60,
        label_config: tuple[list[str], list[str]] | None = None,
        infer_processors: list[Any] | None = None,
        learn_processors: list[Any] | None = None,
        interval: str = "1d",
    ) -> None:
        feat_exprs, feat_names = Alpha360DL.get_feature_config(n_steps=n_steps)
        lbl_exprs, lbl_names = label_config or Alpha360DL.get_label_config()

        loader = AQPDataLoader(
            config={
                "feature": dict(zip(feat_names, feat_exprs, strict=False)),
                "label": dict(zip(lbl_names, lbl_exprs, strict=False)),
            },
            interval=interval,
        )
        super().__init__(
            instruments=instruments,
            start_time=start_time,
            end_time=end_time,
            data_loader=loader,
            infer_processors=infer_processors or _default_infer_processors(),
            learn_processors=learn_processors or _default_learn_processors(),
            fit_start_time=fit_start_time,
            fit_end_time=fit_end_time,
        )
        self.n_steps = int(n_steps)


__all__ = ["Alpha360", "Alpha360DL"]
