"""Forecasters — unified facade + LLM / classical / deep backends.

Two layers live here:

1. :class:`BaseForecaster` — backend-agnostic ``fit`` / ``predict`` /
   ``predict_quantiles`` contract mirroring sktime. Concrete adapters
   (``statsmodels``, ``prophet``, ``sktime``, ``auto_arima``) slot in via
   ``list_by_kind('forecaster')``.

2. :class:`FinGPTForecaster` — LLM-powered directional forecaster
   (news + fundamentals → next-week direction). Retained with its
   original surface so the existing :class:`ForecasterAlpha` adapter
   keeps working unchanged.
"""
from __future__ import annotations

import contextlib as _contextlib

from aqp_models.applications.forecaster.alpha import ForecasterAlpha
from aqp_models.applications.forecaster.base import (
    BaseForecaster,
    ForecastResult,
    NaiveForecaster,
)
from aqp_models.applications.forecaster.forecaster import (
    FinGPTForecaster,
    ForecasterOutput,
)

# Optional backends — lazy imports so the base install remains lean.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_models.applications.forecaster.statsmodels_adapter import (  # noqa: F401
        ARIMAForecaster,
        SARIMAXForecaster,
        VARForecaster,
        VECMForecaster,
    )
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_models.applications.forecaster.prophet_adapter import ProphetForecaster  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_models.applications.forecaster.sktime_adapter import SktimeForecaster  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_models.applications.forecaster.auto_arima import AutoARIMAForecaster  # noqa: F401

__all__ = [
    "BaseForecaster",
    "FinGPTForecaster",
    "ForecastResult",
    "ForecasterAlpha",
    "ForecasterOutput",
    "NaiveForecaster",
]
