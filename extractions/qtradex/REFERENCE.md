# QTradeX-AI-Agents — Extraction Reference

**Source:** `inspiration/QTradeX-AI-Agents-master/`
**Upstream:** https://github.com/squidKid-deluxe/QTradeX-Algo-Trading-SDK

## Repo character

A library of 28 rule-based crypto trading bots built on the proprietary `qtradex` SDK. Each `*.py` defines a `class XxxBot(qx.BaseBot)` with:

- `indicators(self, data)` — feature compute via `qx.ti.*` (Tulipy-style) or `qx.qi.*` (extended)
- `strategy(self, state, indicators)` — returns `qx.Buy()`, `qx.Sell()`, `None`, or `qx.Thresholds(...)`
- `fitness(...)` — list of metric tokens (`roi_gross`, `sortino_ratio`, `trade_win_rate`)
- `main()` — `qx.dispatch(bot, qx.Data(...), qx.PaperWallet(...))`

## AQP target mapping

All 28 strategies port to `aqp/strategies/qtradex/<snake_name>.py` as `IAlphaModel` subclasses (decorated `@register("Name", source="qtradex", category="...")`). YAMLs land in `configs/strategies/qtradex/<name>.yaml`.

`qx.ti.*` calls map to `aqp/data/indicators_zoo.py` entries; missing indicators (KST, RAVI, FRAMA, Vortex, Fisher, etc.) get added to `aqp/core/indicators.py::ALL_INDICATORS` in Phase 1.B.

Discrete-policy `tunes/` JSON ride along under `configs/strategies/qtradex/_tunes/`.

---

## Aroon

**Source:** `aroon.py`
**Class:** `Aroon`
**Logic:** Aroon oscillator (`qx.ti.aroonosc(period)`) crosses up/down through buy/sell thresholds.
**Tunable params:** `period`, `buy_thresh`, `sell_thresh`.
**AQP target:** `aqp/strategies/qtradex/aroon.py::AroonAlpha`. Use `IndicatorZoo` `AroonOsc:14` (added to ALL_INDICATORS in Phase 1.B).
**Category:** `momentum`.

```python
def indicators(self, data):
    return {"aroon_osc": qx.ti.aroonosc(data["high"], data["low"], self.tune["period"])}

def strategy(self, state, indicators):
    if indicators["aroon_osc"][-1] > self.tune["buy_thresh"]:
        return qx.Buy()
    if indicators["aroon_osc"][-1] < self.tune["sell_thresh"]:
        return qx.Sell()
    return None
```

---

## AroonMfiVwap

**Source:** `aroon_mfi_vwap.py`
**Class:** `AroonMfiVwap`
**Logic:** Aroon spread + short EMA vs VWAP + MFI for entries.
**AQP target:** `aqp/strategies/qtradex/aroon_mfi_vwap.py::AroonMfiVwapAlpha`. Needs `MFI` and `AnchoredVWAP` added to ALL_INDICATORS.
**Category:** `momentum_volume`.

---

## BlackHoleStrategy

**Source:** `blackhole.py`
**Class:** `BlackHoleStrategy`
**Logic:** "Black hole" low-ATR compression detection (`atr < lookback_mean * compression_ratio`) → momentum breakout. Optional limit bands via `qx.Thresholds`.
**AQP target:** `aqp/strategies/qtradex/blackhole.py::BlackHoleAlpha`. Uses new `aqp/data/regime.py::BlackHoleZone` helper.
**Category:** `volatility_breakout`.

---

## ClassicalCryptoBot

**Source:** `classic_crypto_bot.py`
**Class:** `ClassicalCryptoBot`
**Logic:** SMA/EMA/RSI/Stochastic/ADX threshold stack — buy when all bullish.
**AQP target:** `aqp/strategies/qtradex/classical.py::ClassicalCryptoAlpha`.
**Category:** `composite_momentum`.

---

## Confluence

**Source:** `confluence.py`
**Class:** `Confluence`
**Logic:** EMA trend + RSI + MACD histogram + Bollinger location confluence.
**AQP target:** `aqp/strategies/qtradex/confluence.py::ConfluenceAlpha`.
**Category:** `composite_momentum`.

---

## CryptoMasterBot

**Source:** `cryptomasterbot.py`
**Class:** `CryptoMasterBot`
**Logic:** Broad classic stack (MACD, RSI, BBands, Fisher, Stoch, ADX, volume).
**AQP target:** `aqp/strategies/qtradex/master.py::CryptoMasterAlpha`. Needs `Fisher` indicator.
**Category:** `composite_momentum`.

---

## Cthulhu

**Source:** `cthulhu.py`
**Class:** `Cthulhu`
**Logic:** EMA + standard-deviation channels with PSAR interaction.
**AQP target:** `aqp/strategies/qtradex/cthulhu.py::CthulhuAlpha`.
**Category:** `channel_breakout`.

---

## DirectionalMovement

**Source:** `directional_movement.py`
**Class:** `DirectionalMovement`
**Logic:** Triple EMA + DM (`+DI`/`-DI`) + ADX/ADXR directional system.
**AQP target:** `aqp/strategies/qtradex/dmi.py::DirectionalMovementAlpha`.
**Category:** `trend`.

---

## EmaCrossSMA (was `EmaCross` in `ema_cross.py`)

**Source:** `ema_cross.py`
**Class:** `EmaCross`
**Logic:** SMA envelope (`top`/`bottom`) vs long SMA crossover-style bands.
**AQP target:** `aqp/strategies/qtradex/ema_cross_sma.py::EmaCrossSMAAlpha`.
**Category:** `trend`.

---

## EmaCrossHA (was `EmaCross` in `heiken_ashi.py`)

**Source:** `heiken_ashi.py`
**Class:** `EmaCross`
**Logic:** Heikin-Ashi SMA envelope cross vs long HA SMA.
**AQP target:** `aqp/strategies/qtradex/ema_cross_ha.py::EmaCrossHAAlpha`. Uses `HA` from existing ALL_INDICATORS.
**Category:** `trend`.

---

## ExtinctionEvent

**Source:** `extinction_event.py`
**Class:** `ExtinctionEvent`
**Logic:** Three EMAs + dynamic bull/bear channels; `qx.Thresholds` + trend override; **custom `execution()` price overrides** (limit orders).
**AQP target:** `aqp/strategies/qtradex/extinction_event.py::ExtinctionEventStrategy` (full `IStrategy`, not just alpha, due to execution override).
**Category:** `regime_channel`.

---

## Forty96

**Source:** `forty96.py`
**Class:** `Forty96`
**Logic:** 12-bit pattern from EMAs/slopes → lookup table in `tune` (4096 entries). Discrete policy.
**AQP target:** `aqp/strategies/qtradex/forty96.py::Forty96Alpha`. Tune table loaded from `configs/strategies/qtradex/_tunes/forty96_4099.json`.
**Category:** `discrete_policy`.

---

## UltimateForecastMesa

**Source:** `fosc_uo_msw.py`
**Class:** `UltimateForecastMesa`
**Logic:** Ultimate oscillator + forecast oscillator + Mesa sine wave with vote thresholds.
**AQP target:** `aqp/strategies/qtradex/ultimate_forecast.py::UltimateForecastMesaAlpha`. Needs `MesaSineWave` indicator.
**Category:** `oscillator_ensemble`.

---

## FRAMABot

**Source:** `frama.py`
**Class:** `FRAMABot`
**Logic:** Price vs Fractal Adaptive Moving Average cross.
**AQP target:** `aqp/strategies/qtradex/frama.py::FRAMABotAlpha`. Needs `FRAMA` indicator.
**Category:** `adaptive_trend`.

---

## ParabolicSARBot (canonical)

**Source:** `harmonica.py` (canonical, supersedes `parabolic_ten.py`)
**Class:** `ParabolicSARBot`
**Logic:** Six PSARs at varying acceleration factors + four EMAs for reversal/trend confirmation.
**AQP target:** `aqp/strategies/qtradex/parabolic_sar.py::ParabolicSARBotAlpha`. Uses existing `PSAR`.
**Category:** `multi_param_trend`.

---

## IchimokuBot

**Source:** `ichimoku.py`
**Class:** `IchimokuBot`
**Logic:** Senkou span A/B cloud cross signals.
**AQP target:** `aqp/strategies/qtradex/ichimoku.py::IchimokuBotAlpha`. Uses existing `Ichimoku`.
**Category:** `cloud`.

---

## IChing

**Source:** `iching.py`
**Class:** `IChing`
**Logic:** Six EMA slopes → 6-bit pattern → tunable discrete policy (64 entries).
**AQP target:** `aqp/strategies/qtradex/iching.py::IChingAlpha`. Tune from `_tunes/iching_70.json`.
**Category:** `discrete_policy`.

---

## KSTIndicatorBot

**Source:** `kst.py`
**Class:** `KSTIndicatorBot`
**Logic:** KST (Know Sure Thing) vs KST signal-line cross.
**AQP target:** `aqp/strategies/qtradex/kst.py::KSTIndicatorBotAlpha`. Needs `KST` indicator.
**Category:** `oscillator`.

---

## LavaHK

**Source:** `lava_hkbot.py`
**Class:** `LavaHK`
**Logic:** Dual EMA + OHLC4 "mode" heuristic for signals.
**AQP target:** `aqp/strategies/qtradex/lava_hk.py::LavaHKAlpha`.
**Category:** `composite_trend`.

---

## MASabres

**Source:** `ma_sabres.py`
**Class:** `MASabres`
**Logic:** Five selectable MA types (SMA, EMA, WMA, HMA, KAMA); slope normalization → bullish/bearish votes → buy/sell when consensus crosses threshold.
**AQP target:** `aqp/strategies/qtradex/ma_sabres.py::MASabresAlpha`. Uses new `aqp/data/regime.py::MultiMASlopeVote`.
**Category:** `consensus_trend`.
**Test selected:** Yes — Phase 10 strategy backtest uses this via `EventDrivenBacktester`.

---

## BBadXMacDrSi

**Source:** `mac_dr_si.py`
**Class:** `BBadXMacDrSi`
**Logic:** MACD + RSI + FFT-domain low-pass filter (Butterworth via scipy) + ADX regime gate (trend vs range mode).
**AQP target:** `aqp/strategies/qtradex/bbadx_mac_dr_si.py::BBadXMacDrSiAlpha`. Uses new `aqp/data/regime.py::ADXRegimeClassifier`.
**Category:** `regime_aware_oscillator`.
**Note:** Only QTradeX strategy needing scipy.

---

## MasterBot

**Source:** `masterbot.py`
**Class:** `MasterBot`
**Logic:** MACD + Stochastic + RSI + ATR confirmation.
**AQP target:** `aqp/strategies/qtradex/master_classic.py::MasterBotAlpha`.
**Category:** `composite_oscillator`.

---

## RenkoBot (was `Renko` in `renko.py`)

**Source:** `renko.py`
**Class:** `Renko`
**Logic:** Renko brick construction + RSI directional logic.
**AQP target:** `aqp/strategies/qtradex/renko.py::RenkoBotAlpha`. Uses existing `Renko` indicator.
**Category:** `chart_type`.

---

## HeikinAshiIchimokuVortexBot

**Source:** `smi_adaptive_ravi.py`
**Class:** `HeikinAshiIchimokuVortexBot`
**Logic:** Heikin-Ashi + Ichimoku + KST + FRAMA + RAVI + SMI + Vortex; boolean vote count vs threshold.
**AQP target:** `aqp/strategies/qtradex/composite_haichi.py::HeikinAshiIchimokuVortexAlpha`. Needs `RAVI`, `Vortex`.
**Category:** `composite`.

---

## TradFiInspired

**Source:** `tradfibot.py`
**Class:** `TradFiInspired`
**Logic:** Multi-classical-indicator vote count ≥ thresholds (TradFi-style).
**AQP target:** `aqp/strategies/qtradex/tradfi.py::TradFiInspiredAlpha`. Tool wrap available as `multi_indicator_vote_tool` in Phase 7.
**Category:** `consensus_voting`.

---

## TrimaZlemaFisher

**Source:** `trima_zlema_fischer.py`
**Class:** `TrimaZlemaFisher`
**Logic:** TRIMA/ZLEMA/Fisher transform derivatives for momentum flips.
**AQP target:** `aqp/strategies/qtradex/trima_zlema.py::TrimaZlemaFisherAlpha`. Needs `Fisher`.
**Category:** `smooth_momentum`.

---

## VortexIndicatorBot

**Source:** `vortex.py`
**Class:** `VortexIndicatorBot`
**Logic:** Vortex `+VI` vs `-VI` cross.
**AQP target:** `aqp/strategies/qtradex/vortex.py::VortexAlpha`. Needs `Vortex`.
**Category:** `trend`.

---

## (Skipped) `qi_indicators_test.py`

Indicator survey only — `strategy()` references undefined `random` symbol. Not registered.

## Common QTradeX → AQP refactoring

- Replace `qx.Buy()` / `qx.Sell()` returns with `Signal(symbol=..., direction=..., score=...)` lists in `IAlphaModel.generate_signals`.
- Replace `qx.PaperWallet` / `qx.Data` / `qx.dispatch` in `main()` with a YAML config under `configs/strategies/qtradex/<name>.yaml` consumed by `run_backtest_from_config`.
- Replace `qx.derivative(series)` with `series.diff()` (pandas) or `np.diff(arr, prepend=arr[0])` (numpy).
- Replace `qx.truncate(*arrays)` with right-aligned slicing using the shortest length.
