package io.rpi.flink.indicators.volume;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MInteger;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * Volume indicators: AD (Chaikin A/D Line), ADOSC (Chaikin Oscillator), OBV
 * (On-Balance Volume).
 */
public final class VolumeIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;

    public VolumeIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("volume", bufferSize, windowSizeSec);
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
        double[] volumes = TaLibCore.volumes(history);
        double[] out = new double[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        try {
            core.ad(0, n - 1, highs, lows, closes, volumes, begIdx, nbElem, out);
            record.put("ad", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }

        try {
            core.adOsc(0, n - 1, highs, lows, closes, volumes, 3, 10, begIdx, nbElem, out);
            record.put("adosc", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }

        try {
            core.obv(0, n - 1, closes, volumes, begIdx, nbElem, out);
            record.put("obv", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
    }
}
