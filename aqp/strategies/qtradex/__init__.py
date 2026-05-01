"""QTradeX-AI-Agents strategy ports.

28 rule-based crypto bots originally written against the proprietary
``qtradex`` SDK. Re-implemented here as ``IAlphaModel`` subclasses
consuming AQP's bar interface. See
``extractions/qtradex/REFERENCE.md`` for per-strategy notes.
"""
from __future__ import annotations

from aqp.strategies.qtradex.alphas import (
    AroonAlpha,
    AroonMfiVwapAlpha,
    BBadXMacDrSiAlpha,
    BasicAlphaBase,
    BlackHoleAlpha,
    ClassicalCryptoAlpha,
    ConfluenceAlpha,
    CryptoMasterAlpha,
    CthulhuAlpha,
    DirectionalMovementAlpha,
    EmaCrossHAAlpha,
    EmaCrossSMAAlpha,
    ExtinctionEventAlpha,
    FRAMABotAlpha,
    Forty96Alpha,
    HeikinAshiIchimokuVortexAlpha,
    IChingAlpha,
    IchimokuBotAlpha,
    KSTIndicatorBotAlpha,
    LavaHKAlpha,
    MASabresAlpha,
    MasterBotAlpha,
    ParabolicSARBotAlpha,
    RenkoBotAlpha,
    TradFiInspiredAlpha,
    TrimaZlemaFisherAlpha,
    UltimateForecastMesaAlpha,
    VortexAlpha,
)


__all__ = [
    "AroonAlpha",
    "AroonMfiVwapAlpha",
    "BBadXMacDrSiAlpha",
    "BasicAlphaBase",
    "BlackHoleAlpha",
    "ClassicalCryptoAlpha",
    "ConfluenceAlpha",
    "CryptoMasterAlpha",
    "CthulhuAlpha",
    "DirectionalMovementAlpha",
    "EmaCrossHAAlpha",
    "EmaCrossSMAAlpha",
    "ExtinctionEventAlpha",
    "FRAMABotAlpha",
    "Forty96Alpha",
    "HeikinAshiIchimokuVortexAlpha",
    "IChingAlpha",
    "IchimokuBotAlpha",
    "KSTIndicatorBotAlpha",
    "LavaHKAlpha",
    "MASabresAlpha",
    "MasterBotAlpha",
    "ParabolicSARBotAlpha",
    "RenkoBotAlpha",
    "TradFiInspiredAlpha",
    "TrimaZlemaFisherAlpha",
    "UltimateForecastMesaAlpha",
    "VortexAlpha",
]
