package io.rpi.flink.indicators.pricetx;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MInteger;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * Price transform indicators: AVGPRICE, MEDPRICE, TYPPRICE, WCLPRICE.
 * These are per-bar aggregations (no history required beyond the current
 * OHLC), but we compute them in the same pipeline for consistency.
 */
public final class PriceTransformIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;

    public PriceTransformIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("price_transform", bufferSize, windowSizeSec);
    }

    @Override
    protected void compute(String symbol, List<MarketBar> history, IndicatorRecord record) {
        int n = history.size();
        if (n == 0) {
            return;
        }
        Core core = TaLibCore.get();
        double[] opens = TaLibCore.opens(history);
        double[] highs = TaLibCore.highs(history);
        double[] lows = TaLibCore.lows(history);
        double[] closes = TaLibCore.closes(history);
        double[] out = new double[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        try {
            core.avgPrice(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out);
            record.put("avgprice", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.medPrice(0, n - 1, highs, lows, begIdx, nbElem, out);
            record.put("medprice", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.typPrice(0, n - 1, highs, lows, closes, begIdx, nbElem, out);
            record.put("typprice", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
        try {
            core.wclPrice(0, n - 1, highs, lows, closes, begIdx, nbElem, out);
            record.put("wclprice", TaLibCore.last(out, nbElem));
        } catch (Exception ignored) {
        }
    }
}
