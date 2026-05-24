package io.rpi.flink.indicators.overlap;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MAType;
import com.tictactec.ta.lib.MInteger;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * Overlap studies - moving averages + Bollinger Bands + SAR.
 *
 * <p>TA-Lib functions: SMA, EMA, WMA, DEMA, TEMA, TRIMA, KAMA, MAMA, T3,
 * BBANDS, MIDPOINT, MIDPRICE, SAR, SAREXT, HT_TRENDLINE.</p>
 */
public final class OverlapIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;

    public OverlapIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("overlap", bufferSize, windowSizeSec);
    }

    @Override
    protected void compute(String symbol, List<MarketBar> history, IndicatorRecord record) {
        int n = history.size();
        if (n < 2) {
            return;
        }
        Core core = TaLibCore.get();
        double[] closes = TaLibCore.closes(history);
        double[] highs = TaLibCore.highs(history);
        double[] lows = TaLibCore.lows(history);
        double[] out = new double[n];
        double[] out2 = new double[n];
        double[] out3 = new double[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        putMa(core, closes, n, 5, record, "sma_5", MAType.Sma);
        putMa(core, closes, n, 10, record, "sma_10", MAType.Sma);
        putMa(core, closes, n, 20, record, "sma_20", MAType.Sma);
        putMa(core, closes, n, 50, record, "sma_50", MAType.Sma);
        putMa(core, closes, n, 12, record, "ema_12", MAType.Ema);
        putMa(core, closes, n, 26, record, "ema_26", MAType.Ema);
        putMa(core, closes, n, 20, record, "wma_20", MAType.Wma);
        putMa(core, closes, n, 20, record, "dema_20", MAType.Dema);
        putMa(core, closes, n, 20, record, "tema_20", MAType.Tema);
        putMa(core, closes, n, 20, record, "trima_20", MAType.Trima);
        putMa(core, closes, n, 30, record, "kama_30", MAType.Kama);
        putMa(core, closes, n, 5, record, "t3_5", MAType.T3);

        // MAMA: adaptive moving average
        core.mama(0, n - 1, closes, 0.5, 0.05, begIdx, nbElem, out, out2);
        record.put("mama", TaLibCore.last(out, nbElem));
        record.put("mama_fama", TaLibCore.last(out2, nbElem));

        // Bollinger Bands
        core.bbands(0, n - 1, closes, 20, 2.0, 2.0, MAType.Sma, begIdx, nbElem, out, out2, out3);
        record.put("bb_upper", TaLibCore.last(out, nbElem));
        record.put("bb_middle", TaLibCore.last(out2, nbElem));
        record.put("bb_lower", TaLibCore.last(out3, nbElem));

        // MIDPOINT / MIDPRICE
        core.midPoint(0, n - 1, closes, 14, begIdx, nbElem, out);
        record.put("midpoint_14", TaLibCore.last(out, nbElem));

        if (highs.length == n && lows.length == n) {
            core.midPrice(0, n - 1, highs, lows, 14, begIdx, nbElem, out);
            record.put("midprice_14", TaLibCore.last(out, nbElem));

            core.sar(0, n - 1, highs, lows, 0.02, 0.2, begIdx, nbElem, out);
            record.put("sar", TaLibCore.last(out, nbElem));

            core.sarExt(0, n - 1, highs, lows,
                    0.0, 0.0, 0.02, 0.02, 0.2,
                    0.02, 0.02, 0.2,
                    begIdx, nbElem, out);
            record.put("sarext", TaLibCore.last(out, nbElem));
        }

        // HT_TRENDLINE needs >= 63 bars
        if (n >= 63) {
            core.htTrendline(0, n - 1, closes, begIdx, nbElem, out);
            record.put("ht_trendline", TaLibCore.last(out, nbElem));
        }
    }

    private void putMa(Core core, double[] closes, int n, int period,
                       IndicatorRecord record, String name, MAType type) {
        if (n <= period) {
            return;
        }
        double[] out = new double[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();
        core.movingAverage(0, n - 1, closes, period, type, begIdx, nbElem, out);
        record.put(name, TaLibCore.last(out, nbElem));
    }
}
