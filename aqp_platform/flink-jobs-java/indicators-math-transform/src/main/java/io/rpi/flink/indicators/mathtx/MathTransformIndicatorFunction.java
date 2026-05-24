package io.rpi.flink.indicators.mathtx;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MInteger;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * Math transform functions (element-wise): ACOS, ASIN, ATAN, CEIL, COS,
 * COSH, EXP, FLOOR, LN, LOG10, SIN, SINH, SQRT, TAN, TANH.
 */
public final class MathTransformIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;

    public MathTransformIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("math_transform", bufferSize, windowSizeSec);
    }

    @Override
    protected void compute(String symbol, List<MarketBar> history, IndicatorRecord record) {
        int n = history.size();
        if (n == 0) {
            return;
        }
        Core core = TaLibCore.get();
        double[] closes = TaLibCore.closes(history);
        double[] out = new double[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        // Most transforms are defined only over [-1, 1] or >0 domains; we still
        // invoke them and filter NaNs via IndicatorRecord.put.
        try { core.acos(0, n - 1, closes, begIdx, nbElem, out); record.put("acos", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.asin(0, n - 1, closes, begIdx, nbElem, out); record.put("asin", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.atan(0, n - 1, closes, begIdx, nbElem, out); record.put("atan", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.ceil(0, n - 1, closes, begIdx, nbElem, out); record.put("ceil", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.cos(0, n - 1, closes, begIdx, nbElem, out); record.put("cos", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.cosh(0, n - 1, closes, begIdx, nbElem, out); record.put("cosh", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.exp(0, n - 1, closes, begIdx, nbElem, out); record.put("exp", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.floor(0, n - 1, closes, begIdx, nbElem, out); record.put("floor", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.ln(0, n - 1, closes, begIdx, nbElem, out); record.put("ln", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.log10(0, n - 1, closes, begIdx, nbElem, out); record.put("log10", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.sin(0, n - 1, closes, begIdx, nbElem, out); record.put("sin", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.sinh(0, n - 1, closes, begIdx, nbElem, out); record.put("sinh", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.sqrt(0, n - 1, closes, begIdx, nbElem, out); record.put("sqrt", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.tan(0, n - 1, closes, begIdx, nbElem, out); record.put("tan", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
        try { core.tanh(0, n - 1, closes, begIdx, nbElem, out); record.put("tanh", TaLibCore.last(out, nbElem)); } catch (Exception ignored) {}
    }
}
