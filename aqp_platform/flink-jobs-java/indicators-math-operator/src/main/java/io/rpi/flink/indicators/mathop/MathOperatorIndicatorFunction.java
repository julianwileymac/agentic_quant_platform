package io.rpi.flink.indicators.mathop;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MInteger;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * Math operators (rolling window reductions): ADD, DIV, MAX, MAXINDEX, MIN,
 * MININDEX, MINMAX, MINMAXINDEX, MULT, SUB, SUM.
 *
 * <p>For pairwise operators (ADD/DIV/MULT/SUB) we compute
 * {@code f(high, low)} as a representative demonstration; adapt to taste
 * when extending.</p>
 */
public final class MathOperatorIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;

    public MathOperatorIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("math_operator", bufferSize, windowSizeSec);
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
        int[] iOut = new int[n];
        int[] iOut2 = new int[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        try { core.add(0, n - 1, highs, lows, begIdx, nbElem, out); record.put("add_hl", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.div(0, n - 1, highs, lows, begIdx, nbElem, out); record.put("div_hl", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.sub(0, n - 1, highs, lows, begIdx, nbElem, out); record.put("sub_hl", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.mult(0, n - 1, highs, lows, begIdx, nbElem, out); record.put("mult_hl", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}

        try { core.max(0, n - 1, closes, 30, begIdx, nbElem, out); record.put("max_30", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.min(0, n - 1, closes, 30, begIdx, nbElem, out); record.put("min_30", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.sum(0, n - 1, closes, 30, begIdx, nbElem, out); record.put("sum_30", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}

        try {
            core.maxIndex(0, n - 1, closes, 30, begIdx, nbElem, iOut);
            if (nbElem.value > 0) record.put("maxindex_30", iOut[nbElem.value - 1]);
        } catch (Exception ignored) {}
        try {
            core.minIndex(0, n - 1, closes, 30, begIdx, nbElem, iOut);
            if (nbElem.value > 0) record.put("minindex_30", iOut[nbElem.value - 1]);
        } catch (Exception ignored) {}
        try {
            core.minMax(0, n - 1, closes, 30, begIdx, nbElem, out, out2);
            record.put("minmax_min_30", TaLibCore.last(out, nbElem));
            record.put("minmax_max_30", TaLibCore.last(out2, nbElem));
        } catch (Exception ignored) {}
        try {
            core.minMaxIndex(0, n - 1, closes, 30, begIdx, nbElem, iOut, iOut2);
            if (nbElem.value > 0) {
                record.put("minmaxindex_min_30", iOut[nbElem.value - 1]);
                record.put("minmaxindex_max_30", iOut2[nbElem.value - 1]);
            }
        } catch (Exception ignored) {}
    }
}
