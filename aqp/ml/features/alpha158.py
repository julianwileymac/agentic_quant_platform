"""Alpha158 feature factory — native port of qlib's ``Alpha158``.

The 158 features split into families:

- K-bar structure (9 features) — OHLC-ratio candle statistics.
- Price lookback (1 feature per field per window) — normalised price refs.
- Volume lookback (1 feature per window) — normalised volume refs.
- Rolling family (many features per window) — ROC, MA, STD, BETA, RSQR,
  RESI, MAX, MIN, QTLU, QTLD, RANK, RSV, IMAX, IMIN, IMXD, CORR, CORD,
  CNTP, CNTN, CNTD, SUMP, SUMN, SUMD, VMA, VSTD, WVMA, VSUMP, VSUMN, VSUMD.

Reference: ``inspiration/qlib-main/qlib/contrib/data/loader.py``
(``Alpha158DL.get_feature_config``).
"""
from __future__ import annotations

from typing import Any

from aqp.core.registry import register
from aqp.ml.handler import DataHandlerLP
from aqp.ml.loader import AQPDataLoader

# ---------------------------------------------------------------------------
# Feature-expression builder (static).
# ---------------------------------------------------------------------------


class Alpha158DL:
    """Static feature-config factory (no state, just expression lists)."""

    DEFAULT_WINDOWS: tuple[int, ...] = (5, 10, 20, 30, 60)

    @staticmethod
    def get_feature_config(
        config: dict[str, Any] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Return ``(exprs, names)`` — list of formula strings + their column
        names. ``config`` overrides any of: ``kbar, price, volume, rolling``.
        """
        config = config or {}
        fields: list[str] = []
        names: list[str] = []

        # -- K-bar features (9) ----------------------------------------
        if config.get("kbar", True):
            kbar_exprs = [
                ("KMID",  "($close - $open) / $open"),
                ("KLEN",  "($high - $low) / $open"),
                ("KMID2", "($close - $open) / ($high - $low + 1e-12)"),
                ("KUP",   "($high - Greater($open, $close)) / $open"),
                ("KUP2",  "($high - Greater($open, $close)) / ($high - $low + 1e-12)"),
                ("KLOW",  "(Less($open, $close) - $low) / $open"),
                ("KLOW2", "(Less($open, $close) - $low) / ($high - $low + 1e-12)"),
                ("KSFT",  "(2 * $close - $high - $low) / $open"),
                ("KSFT2", "(2 * $close - $high - $low) / ($high - $low + 1e-12)"),
            ]
            for n, e in kbar_exprs:
                names.append(n)
                fields.append(e)

        # -- Price lookback --------------------------------------------
        price_cfg = config.get("price", {})
        price_windows: tuple[int, ...] = tuple(price_cfg.get("windows", (0,)))
        price_fields: tuple[str, ...] = tuple(price_cfg.get("feature", ("OPEN", "HIGH", "LOW", "VWAP")))
        for field in price_fields:
            for w in price_windows:
                if w == 0:
                    fields.append(f"${field.lower()} / $close")
                    names.append(f"{field}0")
                else:
                    fields.append(f"Ref(${field.lower()}, {w}) / $close")
                    names.append(f"{field}{w}")

        # -- Volume lookback -------------------------------------------
        volume_cfg = config.get("volume", {})
        volume_windows: tuple[int, ...] = tuple(volume_cfg.get("windows", (0,)))
        for w in volume_windows:
            if w == 0:
                fields.append("$volume / ($volume + 1e-12)")
                names.append("VOLUME0")
            else:
                fields.append(f"Ref($volume, {w}) / ($volume + 1e-12)")
                names.append(f"VOLUME{w}")

        # -- Rolling families ------------------------------------------
        rolling_cfg = config.get("rolling", {})
        windows: tuple[int, ...] = tuple(rolling_cfg.get("windows", Alpha158DL.DEFAULT_WINDOWS))
        include = set(rolling_cfg.get("include", []))
        exclude = set(rolling_cfg.get("exclude", []))

        def _want(tag: str) -> bool:
            if include and tag not in include:
                return False
            return tag not in exclude

        for w in windows:
            if _want("ROC"):
                fields.append(f"Ref($close, {w}) / $close")
                names.append(f"ROC{w}")
            if _want("MA"):
                fields.append(f"Mean($close, {w}) / $close")
                names.append(f"MA{w}")
            if _want("STD"):
                fields.append(f"Std($close, {w}) / $close")
                names.append(f"STD{w}")
            if _want("BETA"):
                fields.append(f"Slope($close, {w}) / $close")
                names.append(f"BETA{w}")
            if _want("RSQR"):
                fields.append(f"Rsquare($close, {w})")
                names.append(f"RSQR{w}")
            if _want("RESI"):
                fields.append(f"Resi($close, {w}) / $close")
                names.append(f"RESI{w}")
            if _want("MAX"):
                fields.append(f"Max($high, {w}) / $close")
                names.append(f"MAX{w}")
            if _want("MIN"):
                fields.append(f"Min($low, {w}) / $close")
                names.append(f"MIN{w}")
            if _want("QTLU"):
                fields.append(f"Quantile($close, {w}, 0.8) / $close")
                names.append(f"QTLU{w}")
            if _want("QTLD"):
                fields.append(f"Quantile($close, {w}, 0.2) / $close")
                names.append(f"QTLD{w}")
            if _want("RANK"):
                fields.append("Rank($close)")
                names.append(f"RANK{w}")
            if _want("RSV"):
                fields.append(f"($close - Min($low, {w})) / (Max($high, {w}) - Min($low, {w}) + 1e-12)")
                names.append(f"RSV{w}")
            if _want("IMAX"):
                fields.append(f"IdxMax($high, {w}) / {w}")
                names.append(f"IMAX{w}")
            if _want("IMIN"):
                fields.append(f"IdxMin($low, {w}) / {w}")
                names.append(f"IMIN{w}")
            if _want("IMXD"):
                fields.append(f"(IdxMax($high, {w}) - IdxMin($low, {w})) / {w}")
                names.append(f"IMXD{w}")
            if _want("CORR"):
                fields.append(f"Corr($close, Log($volume + 1), {w})")
                names.append(f"CORR{w}")
            if _want("CORD"):
                fields.append(f"Corr($close / Ref($close, 1), Log($volume / Ref($volume, 1) + 1), {w})")
                names.append(f"CORD{w}")
            if _want("CNTP"):
                fields.append(f"Mean(Gt($close, Ref($close, 1)), {w})")
                names.append(f"CNTP{w}")
            if _want("CNTN"):
                fields.append(f"Mean(Lt($close, Ref($close, 1)), {w})")
                names.append(f"CNTN{w}")
            if _want("CNTD"):
                fields.append(
                    f"Mean(Gt($close, Ref($close, 1)), {w}) - Mean(Lt($close, Ref($close, 1)), {w})"
                )
                names.append(f"CNTD{w}")
            if _want("SUMP"):
                fields.append(
                    f"Sum(Greater($close - Ref($close, 1), 0), {w}) / "
                    f"(Sum(Abs($close - Ref($close, 1)), {w}) + 1e-12)"
                )
                names.append(f"SUMP{w}")
            if _want("SUMN"):
                fields.append(
                    f"Sum(Greater(Ref($close, 1) - $close, 0), {w}) / "
                    f"(Sum(Abs($close - Ref($close, 1)), {w}) + 1e-12)"
                )
                names.append(f"SUMN{w}")
            if _want("SUMD"):
                fields.append(
                    f"(Sum(Greater($close - Ref($close, 1), 0), {w}) - "
                    f"Sum(Greater(Ref($close, 1) - $close, 0), {w})) / "
                    f"(Sum(Abs($close - Ref($close, 1)), {w}) + 1e-12)"
                )
                names.append(f"SUMD{w}")
            if _want("VMA"):
                fields.append(f"Mean($volume, {w}) / ($volume + 1e-12)")
                names.append(f"VMA{w}")
            if _want("VSTD"):
                fields.append(f"Std($volume, {w}) / ($volume + 1e-12)")
                names.append(f"VSTD{w}")
            if _want("WVMA"):
                fields.append(
                    f"Std(Abs($close / Ref($close, 1) - 1) * $volume, {w}) / "
                    f"(Mean(Abs($close / Ref($close, 1) - 1) * $volume, {w}) + 1e-12)"
                )
                names.append(f"WVMA{w}")
            if _want("VSUMP"):
                fields.append(
                    f"Sum(Greater($volume - Ref($volume, 1), 0), {w}) / "
                    f"(Sum(Abs($volume - Ref($volume, 1)), {w}) + 1e-12)"
                )
                names.append(f"VSUMP{w}")
            if _want("VSUMN"):
                fields.append(
                    f"Sum(Greater(Ref($volume, 1) - $volume, 0), {w}) / "
                    f"(Sum(Abs($volume - Ref($volume, 1)), {w}) + 1e-12)"
                )
                names.append(f"VSUMN{w}")
            if _want("VSUMD"):
                fields.append(
                    f"(Sum(Greater($volume - Ref($volume, 1), 0), {w}) - "
                    f"Sum(Greater(Ref($volume, 1) - $volume, 0), {w})) / "
                    f"(Sum(Abs($volume - Ref($volume, 1)), {w}) + 1e-12)"
                )
                names.append(f"VSUMD{w}")

        return fields, names

    @staticmethod
    def get_label_config() -> tuple[list[str], list[str]]:
        """Default label: 2-day forward return (qlib default)."""
        return (["Ref($close, -2) / Ref($close, -1) - 1"], ["LABEL0"])


# ---------------------------------------------------------------------------
# Data handler.
# ---------------------------------------------------------------------------


@register("Alpha158")
class Alpha158(DataHandlerLP):
    """Drop-in handler returning the Alpha158 feature panel."""

    def __init__(
        self,
        instruments: list[str] | None = None,
        start_time: str | Any = None,
        end_time: str | Any = None,
        fit_start_time: str | Any = None,
        fit_end_time: str | Any = None,
        feature_config: dict[str, Any] | None = None,
        label_config: tuple[list[str], list[str]] | None = None,
        infer_processors: list[Any] | None = None,
        learn_processors: list[Any] | None = None,
        interval: str = "1d",
    ) -> None:
        feat_exprs, feat_names = Alpha158DL.get_feature_config(feature_config)
        lbl_exprs, lbl_names = label_config or Alpha158DL.get_label_config()

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


def _default_infer_processors() -> list[dict[str, Any]]:
    return [
        {
            "class": "Fillna",
            "module_path": "aqp.ml.processors",
            "kwargs": {"fields_group": "feature", "fill_value": 0.0},
        },
        {
            "class": "CSZScoreNorm",
            "module_path": "aqp.ml.processors",
            "kwargs": {"fields_group": "feature"},
        },
    ]


def _default_learn_processors() -> list[dict[str, Any]]:
    return [
        {
            "class": "DropnaLabel",
            "module_path": "aqp.ml.processors",
            "kwargs": {"fields_group": "label"},
        },
    ]


__all__ = ["Alpha158", "Alpha158DL"]
