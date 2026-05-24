package io.rpi.flink.indicators.volatility;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MInteger;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * Volatility indicators: ATR, NATR, TRANGE.
 */
public final class VolatilityIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;

    public VolatilityIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("volatility", bufferSize, windowSizeSec);
    }

    @Override
    protected void compute(String symbol, List<MarketBar> history, IndicatorRecord record) {
        int n = history.size();
        if (n < 2) {
            return;
        }
        Core core = TaLibCore.get();
        double[] highs = TaLibCore.highs(history);
        double[] lows = TaLibCore.lows(history);
        double[] closes = TaLibCore.closes(history);
        double[] out = new double[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        try {
            core.atr(0, n - 1, highs, lows, closes, 14, begIdx, nbElem, out);
            record.put("atr_14", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.natr(0, n - 1, highs, lows, closes, 14, begIdx, nbElem, out);
            record.put("natr_14", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.trueRange(0, n - 1, highs, lows, closes, begIdx, nbElem, out);
            record.put("trange", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
    }
}
