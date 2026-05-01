"""Options pricing & analytics — Bachelier (normal model), inverse, spreads.

Hosts the math from:
- ``inspiration/notebooks-master/Greeks_under_normal_model.ipynb``
- ``inspiration/notebooks-master/inverse_option.ipynb``
- ``inspiration/stock-analysis-engine-master/analysis_engine/build_option_spread_details.py``

Use sub-modules:
    from aqp.options import normal_model, inverse_options, spreads
"""
from __future__ import annotations

from aqp.options import inverse_options, normal_model, spreads

__all__ = ["inverse_options", "normal_model", "spreads"]
