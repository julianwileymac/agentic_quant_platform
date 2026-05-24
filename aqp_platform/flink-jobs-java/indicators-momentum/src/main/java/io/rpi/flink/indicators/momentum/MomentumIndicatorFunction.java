package io.rpi.flink.indicators.momentum;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MAType;
import com.tictactec.ta.lib.MInteger;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * Momentum indicators - the largest single category in TA-Lib.
 *
 * <p>Covers ADX, ADXR, APO, AROON, AROONOSC, BOP, CCI, CMO, DX, MACD,
 * MACDEXT, MACDFIX, MFI, MINUS_DI/DM, PLUS_DI/DM, MOM, PPO, ROC*, RSI,
 * STOCH, STOCHF, STOCHRSI, TRIX, ULTOSC, WILLR.</p>
 */
public final class MomentumIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;

    public MomentumIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("momentum", bufferSize, windowSizeSec);
    }

    @Override
    protected void compute(String symbol, List<MarketBar> history, IndicatorRecord record) {
        int n = history.size();
        if (n < 2) {
            return;
        }
        Core core = TaLibCore.get();
        double[] closes = TaLibCore.closes(history);
        double[] opens = TaLibCore.opens(history);
        double[] highs = TaLibCore.highs(history);
        double[] lows = TaLibCore.lows(history);
        double[] volumes = TaLibCore.volumes(history);
        double[] out = new double[n];
        double[] out2 = new double[n];
        double[] out3 = new double[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        // ADX family
        tryCall(() -> core.adx(0, n - 1, highs, lows, closes, 14, begIdx, nbElem, out),
                record, "adx_14", out, nbElem);
        tryCall(() -> core.adxr(0, n - 1, highs, lows, closes, 14, begIdx, nbElem, out),
                record, "adxr_14", out, nbElem);
        tryCall(() -> core.dx(0, n - 1, highs, lows, closes, 14, begIdx, nbElem, out),
                record, "dx_14", out, nbElem);
        tryCall(() -> core.minusDI(0, n - 1, highs, lows, closes, 14, begIdx, nbElem, out),
                record, "minus_di_14", out, nbElem);
        tryCall(() -> core.minusDM(0, n - 1, highs, lows, 14, begIdx, nbElem, out),
                record, "minus_dm_14", out, nbElem);
        tryCall(() -> core.plusDI(0, n - 1, highs, lows, closes, 14, begIdx, nbElem, out),
                record, "plus_di_14", out, nbElem);
        tryCall(() -> core.plusDM(0, n - 1, highs, lows, 14, begIdx, nbElem, out),
                record, "plus_dm_14", out, nbElem);

        // APO / PPO
        tryCall(() -> core.apo(0, n - 1, closes, 12, 26, MAType.Ema, begIdx, nbElem, out),
                record, "apo", out, nbElem);
        tryCall(() -> core.ppo(0, n - 1, closes, 12, 26, MAType.Ema, begIdx, nbElem, out),
                record, "ppo", out, nbElem);

        // AROON
        if (highs.length == n && lows.length == n) {
            try {
                core.aroon(0, n - 1, highs, lows, 14, begIdx, nbElem, out, out2);
                record.put("aroon_down", TaLibCore.last(out, nbElem));
                record.put("aroon_up", TaLibCore.last(out2, nbElem));
                core.aroonOsc(0, n - 1, highs, lows, 14, begIdx, nbElem, out);
                record.put("aroon_osc", TaLibCore.last(out, nbElem));
            } catch (Exception ignored) {
                // insufficient history
            }
        }

        // BOP
        tryCall(() -> core.bop(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "bop", out, nbElem);

        // CCI
        tryCall(() -> core.cci(0, n - 1, highs, lows, closes, 14, begIdx, nbElem, out),
                record, "cci_14", out, nbElem);

        // CMO
        tryCall(() -> core.cmo(0, n - 1, closes, 14, begIdx, nbElem, out),
                record, "cmo_14", out, nbElem);

        // MACD family
        try {
            core.macd(0, n - 1, closes, 12, 26, 9, begIdx, nbElem, out, out2, out3);
            record.put("macd_line", TaLibCore.last(out, nbElem));
            record.put("macd_signal", TaLibCore.last(out2, nbElem));
            record.put("macd_histogram", TaLibCore.last(out3, nbElem));
            core.macdExt(0, n - 1, closes, 12, MAType.Ema, 26, MAType.Ema, 9, MAType.Ema,
                    begIdx, nbElem, out, out2, out3);
            record.put("macdext_line", TaLibCore.last(out, nbElem));
            record.put("macdfix_signal", TaLibCore.last(out2, nbElem));
        } catch (Exception ignored) {
        }

        // MFI (needs volume)
        tryCall(() -> core.mfi(0, n - 1, highs, lows, closes, volumes, 14, begIdx, nbElem, out),
                record, "mfi_14", out, nbElem);

        // MOM
        tryCall(() -> core.mom(0, n - 1, closes, 10, begIdx, nbElem, out),
                record, "mom_10", out, nbElem);

        // ROC family
        tryCall(() -> core.roc(0, n - 1, closes, 10, begIdx, nbElem, out),
                record, "roc_10", out, nbElem);
        tryCall(() -> core.rocP(0, n - 1, closes, 10, begIdx, nbElem, out),
                record, "rocp_10", out, nbElem);
        tryCall(() -> core.rocR(0, n - 1, closes, 10, begIdx, nbElem, out),
                record, "rocr_10", out, nbElem);
        tryCall(() -> core.rocR100(0, n - 1, closes, 10, begIdx, nbElem, out),
                record, "rocr100_10", out, nbElem);

        // RSI
        tryCall(() -> core.rsi(0, n - 1, closes, 14, begIdx, nbElem, out),
                record, "rsi_14", out, nbElem);

        // Stochastics
        try {
            core.stoch(0, n - 1, highs, lows, closes, 5, 3, MAType.Sma, 3, MAType.Sma,
                    begIdx, nbElem, out, out2);
            record.put("stoch_k", TaLibCore.last(out, nbElem));
            record.put("stoch_d", TaLibCore.last(out2, nbElem));
            core.stochF(0, n - 1, highs, lows, closes, 5, 3, MAType.Sma, begIdx, nbElem, out, out2);
            record.put("stochf_k", TaLibCore.last(out, nbElem));
            record.put("stochf_d", TaLibCore.last(out2, nbElem));
            core.stochRsi(0, n - 1, closes, 14, 5, 3, MAType.Sma, begIdx, nbElem, out, out2);
            record.put("stochrsi_k", TaLibCore.last(out, nbElem));
            record.put("stochrsi_d", TaLibCore.last(out2, nbElem));
        } catch (Exception ignored) {
        }

        // TRIX
        tryCall(() -> core.trix(0, n - 1, closes, 30, begIdx, nbElem, out),
                record, "trix_30", out, nbElem);

        // ULTOSC
        tryCall(() -> core.ultOsc(0, n - 1, highs, lows, closes, 7, 14, 28, begIdx, nbElem, out),
                record, "ultosc", out, nbElem);

        // WILLR
        tryCall(() -> core.willR(0, n - 1, highs, lows, closes, 14, begIdx, nbElem, out),
                record, "willr_14", out, nbElem);
    }

    @FunctionalInterface
    private interface CoreCall {
        void run() throws Exception;
    }

    private void tryCall(CoreCall call, IndicatorRecord record, String name, double[] out, MInteger nb) {
        try {
            call.run();
            record.put(name, TaLibCore.last(out, nb));
        } catch (Exception ignored) {
            // insufficient history or TA-Lib returned an error; skip.
        }
    }
}
