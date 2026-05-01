"""HFT (LOB) strategy stubs.

These subclass :class:`aqp.strategies.lob.LobStrategy` and contain the
signal math from the hftbacktest examples, but the engine integration
is deferred — see ``extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md``.

Calling ``run()`` on any of them today raises ``NotImplementedError``.
"""
from __future__ import annotations

from aqp.strategies.hft.alphas import (
    BasisAlphaMM,
    GLFTMM,
    GridMM,
    ImbalanceAlphaMM,
    QueueAwareMM,
)


__all__ = [
    "BasisAlphaMM",
    "GLFTMM",
    "GridMM",
    "ImbalanceAlphaMM",
    "QueueAwareMM",
]
