package io.rpi.flink.indicators.statistic;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MInteger;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * Statistic functions: BETA, CORREL, LINEARREG, LINEARREG_ANGLE,
 * LINEARREG_INTERCEPT, LINEARREG_SLOPE, STDDEV, TSF, VAR.
 */
public final class StatisticIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;

    public StatisticIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("statistic", bufferSize, windowSizeSec);
    }

    @Override
    protected void compute(String symbol, List<MarketBar> history, IndicatorRecord record) {
        int n = history.size();
        if (n < 5) {
            return;
        }
        Core core = TaLibCore.get();
        double[] closes = TaLibCore.closes(history);
        double[] highs = TaLibCore.highs(history);
        double[] lows = TaLibCore.lows(history);
        double[] out = new double[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        try {
            core.beta(0, n - 1, highs, lows, 5, begIdx, nbElem, out);
            record.put("beta_5", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.correl(0, n - 1, highs, lows, 30, begIdx, nbElem, out);
            record.put("correl_30", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.linearReg(0, n - 1, closes, 14, begIdx, nbElem, out);
            record.put("linearreg_14", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.linearRegAngle(0, n - 1, closes, 14, begIdx, nbElem, out);
            record.put("linearreg_angle_14", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.linearRegIntercept(0, n - 1, closes, 14, begIdx, nbElem, out);
            record.put("linearreg_intercept_14", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.linearRegSlope(0, n - 1, closes, 14, begIdx, nbElem, out);
            record.put("linearreg_slope_14", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.stdDev(0, n - 1, closes, 20, 1.0, begIdx, nbElem, out);
            record.put("stddev_20", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.tsf(0, n - 1, closes, 14, begIdx, nbElem, out);
            record.put("tsf_14", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.variance(0, n - 1, closes, 5, 1.0, begIdx, nbElem, out);
            record.put("var_5", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
    }
}
