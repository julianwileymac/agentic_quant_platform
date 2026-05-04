"""Hugging Face Transformers adapters for ML experiment definitions."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import Model, Reweighter
from aqp.ml.models._utils import predict_to_series, prepare_panel

logger = logging.getLogger(__name__)


@register("HuggingFaceTextSignalModel")
class HuggingFaceTextSignalModel(Model):
    """Score text-bearing datasets with a Transformers pipeline.

    This adapter is intentionally inference-oriented: it can wrap a local or
    Hub checkpoint for text classification / sentiment and turn the positive
    class score into an alpha signal. Numeric-only panels receive neutral
    scores, allowing experiment plans to be validated without a text column.
    """

    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        task: str = "text-classification",
        text_column: str = "text",
        positive_labels: list[str] | None = None,
        negative_labels: list[str] | None = None,
        batch_size: int = 16,
        device: int = -1,
        pipeline_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.model_name = str(model_name)
        self.task = str(task)
        self.text_column = str(text_column)
        self.positive_labels = {s.lower() for s in (positive_labels or ["positive", "bullish", "label_1"])}
        self.negative_labels = {s.lower() for s in (negative_labels or ["negative", "bearish", "label_0"])}
        self.batch_size = int(batch_size)
        self.device = int(device)
        self.pipeline_kwargs = dict(pipeline_kwargs or {})
        self.pipeline_: Any | None = None

    def _ensure_pipeline(self) -> Any:
        if self.pipeline_ is not None:
            return self.pipeline_
        try:
            from transformers import pipeline
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError("transformers is not installed. Install `ml-transformers`.") from exc
        self.pipeline_ = pipeline(
            self.task,
            model=self.model_name,
            device=self.device,
            **self.pipeline_kwargs,
        )
        return self.pipeline_

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> HuggingFaceTextSignalModel:
        del dataset, reweighter
        self._ensure_pipeline()
        return self

    def _extract_text(self, frame: pd.DataFrame) -> pd.Series | None:
        if isinstance(frame.columns, pd.MultiIndex):
            for group in ("feature", "text", "raw"):
                if group not in frame.columns.get_level_values(0):
                    continue
                block = frame[group]
                if self.text_column in block.columns:
                    return block[self.text_column].astype(str)
        if self.text_column in frame.columns:
            return frame[self.text_column].astype(str)
        return None

    def _score_outputs(self, outputs: list[Any]) -> np.ndarray:
        scores: list[float] = []
        for item in outputs:
            candidates = item if isinstance(item, list) else [item]
            score = 0.0
            for cand in candidates:
                label = str(cand.get("label", "")).lower()
                value = float(cand.get("score", 0.0))
                if label in self.positive_labels:
                    score = max(score, value)
                elif label in self.negative_labels:
                    score = min(score, -value)
            scores.append(score)
        return np.asarray(scores, dtype=float)

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        text = self._extract_text(panel)
        if text is None or text.empty:
            return predict_to_series(dataset, seg, np.zeros(len(panel), dtype=float))
        pipe = self._ensure_pipeline()
        outputs = pipe(
            text.fillna("").tolist(),
            batch_size=self.batch_size,
            truncation=True,
            top_k=None,
        )
        return predict_to_series(dataset, seg, self._score_outputs(outputs))


@register("HuggingFaceFinBertSentimentModel", kind="model")
class HuggingFaceFinBertSentimentModel(HuggingFaceTextSignalModel):
    """FinBERT sentiment scorer specialized for financial text.

    Default points at ``ProsusAI/finbert``; override via
    ``settings.hf_finbert_model`` or the constructor.
    """

    def __init__(
        self,
        model_name: str | None = None,
        text_column: str = "text",
        batch_size: int = 16,
        device: int = -1,
        bullish_label: str = "positive",
        bearish_label: str = "negative",
        return_signed: bool = True,
    ) -> None:
        from aqp.config import settings as _settings

        super().__init__(
            model_name=model_name or _settings.hf_finbert_model or "ProsusAI/finbert",
            task="text-classification",
            text_column=text_column,
            positive_labels=[bullish_label, "label_2", "bullish"],
            negative_labels=[bearish_label, "label_0", "bearish"],
            batch_size=batch_size,
            device=device,
        )
        self.return_signed = bool(return_signed)

    def _score_outputs(self, outputs: list[Any]) -> np.ndarray:
        scores = super()._score_outputs(outputs)
        if not self.return_signed:
            scores = np.abs(scores)
        return scores


@register("HuggingFaceTimeSeriesModel", kind="model")
class HuggingFaceTimeSeriesModel(Model):
    """HuggingFace time-series transformer (Informer / TimeSeriesTransformer / PatchTST).

    Wraps the ``transformers`` time-series API where it is available.
    Gated behind ``settings.hf_timeseries_enabled`` because the
    transformers time-series code path is heavy and not always desired
    in a default install.
    """

    def __init__(
        self,
        model_name: str | None = None,
        flavor: str = "time_series_transformer",
        prediction_length: int = 10,
        context_length: int = 60,
        device: int = -1,
        max_inference_rows: int = 1024,
    ) -> None:
        from aqp.config import settings as _settings

        if not getattr(_settings, "hf_timeseries_enabled", False):
            raise RuntimeError(
                "HF time-series support is disabled. "
                "Set AQP_HF_TIMESERIES_ENABLED=true."
            )
        self.model_name = str(
            model_name
            or _settings.hf_timeseries_model
            or "huggingface/time-series-transformer-tourism-monthly"
        )
        self.flavor = str(flavor).lower()
        self.prediction_length = int(prediction_length)
        self.context_length = int(context_length)
        self.device = int(device)
        self.max_inference_rows = int(max_inference_rows)
        self.model_: Any | None = None
        self.tokenizer_: Any | None = None
        self.feature_names_: list[str] = []

    def _load(self) -> None:
        if self.model_ is not None:
            return
        try:
            if self.flavor == "patchtst":
                from transformers import PatchTSTForPrediction as _Cls
            elif self.flavor == "informer":
                from transformers import InformerForPrediction as _Cls
            else:
                from transformers import TimeSeriesTransformerForPrediction as _Cls
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "transformers (with time-series heads) is required. Install `ml-transformers`."
            ) from exc
        self.model_ = _Cls.from_pretrained(self.model_name)
        try:
            import torch  # type: ignore

            if self.device >= 0:
                self.model_ = self.model_.to(f"cuda:{self.device}")
            self.model_.eval()  # type: ignore[attr-defined]
            del torch  # avoid lint warning if torch not used
        except Exception:
            pass

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> HuggingFaceTimeSeriesModel:
        del dataset, reweighter
        # Pretrained inference model — fit() merely loads weights.
        self._load()
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        self._load()
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        # Best-effort: take label column as the univariate target.
        try:
            from aqp.ml.models._utils import split_xy

            _, y, _ = split_xy(panel)
            target = pd.Series(np.asarray(y, dtype=float), index=panel.index, name="label")
        except Exception:
            target = pd.Series(0.0, index=panel.index, name="label")
        if isinstance(target.index, pd.MultiIndex):
            target = target.groupby(level=0).mean()
        target = target.tail(self.max_inference_rows).fillna(0.0).astype(float)

        # Lightweight inference: feed the past_values, ask for forecast, repeat-pad.
        try:
            import torch  # type: ignore

            tensor = torch.tensor(target.values, dtype=torch.float32).unsqueeze(0)
            past_observed_mask = torch.ones_like(tensor)
            time_features = torch.zeros(1, len(target), 1)
            with torch.no_grad():
                out = self.model_.generate(  # type: ignore[union-attr]
                    past_values=tensor[:, -self.context_length:],
                    past_observed_mask=past_observed_mask[:, -self.context_length:],
                    past_time_features=time_features[:, -self.context_length:, :],
                    future_time_features=torch.zeros(1, self.prediction_length, 1),
                )
            sequences = out.sequences.mean(dim=1).squeeze(0).cpu().numpy()
            preds = np.repeat(sequences, max(1, len(panel) // max(1, len(sequences))))
            preds = preds[: len(panel)]
        except Exception as exc:
            logger.debug("HF time-series inference fallback: %s", exc, exc_info=True)
            preds = np.zeros(len(panel), dtype=float)
        return predict_to_series(dataset, seg, preds)


@register("HuggingFaceGenerativeForecastModel", kind="model")
class HuggingFaceGenerativeForecastModel(Model):
    """LLM-driven directional forecast via the AQP router.

    Composes a structured prompt from the latest features and delegates to
    :func:`aqp.llm.providers.router.router_complete` (per hard-rule #2).
    Intended for quick directional priors, not absolute-return forecasting.
    """

    def __init__(
        self,
        model: str | None = None,
        prompt_template: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 64,
    ) -> None:
        self.model = model
        self.prompt_template = (
            prompt_template
            or "You are a directional forecaster. Given features {features}, "
            "respond with a single float in [-1, 1] for next-bar return direction."
        )
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.feature_names_: list[str] = []

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> HuggingFaceGenerativeForecastModel:
        del reweighter
        try:
            from aqp.ml.models._utils import split_xy

            panel = prepare_panel(dataset, "train")
            _, _, features = split_xy(panel)
            self.feature_names_ = features
        except Exception:
            self.feature_names_ = []
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        from aqp.llm.providers.router import router_complete
        from aqp.ml.models._utils import split_xy

        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        X, _, features = split_xy(panel)
        scores = np.zeros(len(X), dtype=float)
        for i in range(len(X)):
            row_summary = ", ".join(
                f"{name}={X[i, j]:.4f}" for j, name in enumerate(features[: min(8, len(features))])
            )
            try:
                resp = router_complete(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": self.prompt_template.format(features=row_summary),
                        }
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                text = str(getattr(resp, "content", resp) or "0").strip()
                # Pull the first float we find.
                import re as _re

                m = _re.search(r"-?\d+(\.\d+)?", text)
                scores[i] = float(m.group(0)) if m else 0.0
                scores[i] = max(-1.0, min(1.0, scores[i]))
            except Exception:
                logger.debug("generative forecast fallback for row %d", i, exc_info=True)
        return predict_to_series(dataset, seg, scores)


__all__ = [
    "HuggingFaceFinBertSentimentModel",
    "HuggingFaceGenerativeForecastModel",
    "HuggingFaceTextSignalModel",
    "HuggingFaceTimeSeriesModel",
]
