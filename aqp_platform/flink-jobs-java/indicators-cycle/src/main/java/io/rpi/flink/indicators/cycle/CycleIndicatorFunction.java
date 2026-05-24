package io.rpi.flink.indicators.cycle;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MInteger;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * Hilbert Transform cycle indicators: HT_DCPERIOD, HT_DCPHASE, HT_PHASOR,
 * HT_SINE, HT_TRENDMODE. All require a minimum of 63 bars of history, so
 * they are skipped silently during warm-up.
 */
public final class CycleIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;
    private static final int HT_MIN_HISTORY = 63;

    public CycleIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("cycle", bufferSize, windowSizeSec);
    }

    @Override
    protected void compute(String symbol, List<MarketBar> history, IndicatorRecord record) {
        int n = history.size();
        if (n < HT_MIN_HISTORY) {
            return;
        }
        Core core = TaLibCore.get();
        double[] closes = TaLibCore.closes(history);
        double[] out = new double[n];
        double[] out2 = new double[n];
        int[] intOut = new int[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        try {
            core.htDcPeriod(0, n - 1, closes, begIdx, nbElem, out);
            record.put("ht_dcperiod", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.htDcPhase(0, n - 1, closes, begIdx, nbElem, out);
            record.put("ht_dcphase", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.htPhasor(0, n - 1, closes, begIdx, nbElem, out, out2);
            record.put("ht_phasor_inphase", TaLibCore.last(out, nbElem));
            record.put("ht_phasor_quadrature", TaLibCore.last(out2, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.htSine(0, n - 1, closes, begIdx, nbElem, out, out2);
            record.put("ht_sine", TaLibCore.last(out, nbElem));
            record.put("ht_leadsine", TaLibCore.last(out2, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.htTrendMode(0, n - 1, closes, begIdx, nbElem, intOut);
            if (nbElem.value > 0) {
                record.put("ht_trendmode", intOut[nbElem.value - 1]);
            }
        } catch (Exception ignored) {
        }
    }
}
