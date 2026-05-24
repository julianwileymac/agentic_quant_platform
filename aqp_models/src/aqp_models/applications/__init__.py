"""FinGPT-inspired ML applications.

Houses extracted models and pipelines from the FinGPT ecosystem:

- :mod:`aqp_models.applications.sentiment` — FinGPT-Sentiment wrapper +
  qlib-style processor.
- :mod:`aqp_models.applications.forecaster` — FinGPT-Forecaster alpha.

Optional deps live in the ``[fingpt]`` extras group (``peft``, ``trl``,
``transformers``, ``bitsandbytes``, ``accelerate``, ``datasets``).
"""
from __future__ import annotations

__all__ = []
