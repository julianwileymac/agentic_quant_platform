package io.rpi.flink.indicators.patterns;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MInteger;
import com.tictactec.ta.lib.RetCode;
import io.rpi.flink.indicators.common.IndicatorFunctionBase;
import io.rpi.flink.indicators.common.IndicatorRecord;
import io.rpi.flink.indicators.common.MarketBar;
import io.rpi.flink.indicators.common.TaLibCore;

import java.util.List;

/**
 * All ~61 candlestick pattern recognizers provided by TA-Lib. Each function
 * returns +100, 0, or -100 for the most recent bar; we translate that into
 * an {@link IndicatorRecord} entry named after the TA-Lib function.
 *
 * <p>Pattern function reference:
 * <a href="https://ta-lib.org/function.html">ta-lib.org/function.html</a>.
 * </p>
 */
public final class PatternsIndicatorFunction extends IndicatorFunctionBase {

    private static final long serialVersionUID = 1L;

    public PatternsIndicatorFunction(int bufferSize, int windowSizeSec) {
        super("patterns", bufferSize, windowSizeSec);
    }

    @Override
    protected void compute(String symbol, List<MarketBar> history, IndicatorRecord record) {
        int n = history.size();
        if (n < 3) {
            return;
        }
        Core core = TaLibCore.get();
        double[] opens = TaLibCore.opens(history);
        double[] highs = TaLibCore.highs(history);
        double[] lows = TaLibCore.lows(history);
        double[] closes = TaLibCore.closes(history);
        int[] out = new int[n];
        MInteger begIdx = new MInteger();
        MInteger nbElem = new MInteger();

        invoke(() -> core.cdl2Crows(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdl2crows", out, nbElem);
        invoke(() -> core.cdl3BlackCrows(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdl3blackcrows", out, nbElem);
        invoke(() -> core.cdl3Inside(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdl3inside", out, nbElem);
        invoke(() -> core.cdl3LineStrike(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdl3linestrike", out, nbElem);
        invoke(() -> core.cdl3Outside(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdl3outside", out, nbElem);
        invoke(() -> core.cdl3StarsInSouth(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdl3starsinsouth", out, nbElem);
        invoke(() -> core.cdl3WhiteSoldiers(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdl3whitesoldiers", out, nbElem);
        invoke(() -> core.cdlAbandonedBaby(0, n - 1, opens, highs, lows, closes, 0.3, begIdx, nbElem, out),
                record, "cdlabandonedbaby", out, nbElem);
        invoke(() -> core.cdlAdvanceBlock(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdladvanceblock", out, nbElem);
        invoke(() -> core.cdlBeltHold(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlbelthold", out, nbElem);
        invoke(() -> core.cdlBreakaway(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlbreakaway", out, nbElem);
        invoke(() -> core.cdlClosingMarubozu(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlclosingmarubozu", out, nbElem);
        invoke(() -> core.cdlConcealBabysWall(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlconcealbabyswall", out, nbElem);
        invoke(() -> core.cdlCounterAttack(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlcounterattack", out, nbElem);
        invoke(() -> core.cdlDarkCloudCover(0, n - 1, opens, highs, lows, closes, 0.5, begIdx, nbElem, out),
                record, "cdldarkcloudcover", out, nbElem);
        invoke(() -> core.cdlDoji(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdldoji", out, nbElem);
        invoke(() -> core.cdlDojiStar(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdldojistar", out, nbElem);
        invoke(() -> core.cdlDragonflyDoji(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdldragonflydoji", out, nbElem);
        invoke(() -> core.cdlEngulfing(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlengulfing", out, nbElem);
        invoke(() -> core.cdlEveningDojiStar(0, n - 1, opens, highs, lows, closes, 0.3, begIdx, nbElem, out),
                record, "cdleveningdojistar", out, nbElem);
        invoke(() -> core.cdlEveningStar(0, n - 1, opens, highs, lows, closes, 0.3, begIdx, nbElem, out),
                record, "cdleveningstar", out, nbElem);
        invoke(() -> core.cdlGapSideSideWhite(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlgapsidesidewhite", out, nbElem);
        invoke(() -> core.cdlGravestoneDoji(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlgravestonedoji", out, nbElem);
        invoke(() -> core.cdlHammer(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlhammer", out, nbElem);
        invoke(() -> core.cdlHangingMan(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlhangingman", out, nbElem);
        invoke(() -> core.cdlHarami(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlharami", out, nbElem);
        invoke(() -> core.cdlHaramiCross(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlharamicross", out, nbElem);
        invoke(() -> core.cdlHignWave(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlhighwave", out, nbElem);
        invoke(() -> core.cdlHikkake(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlhikkake", out, nbElem);
        invoke(() -> core.cdlHikkakeMod(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlhikkakemod", out, nbElem);
        invoke(() -> core.cdlHomingPigeon(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlhomingpigeon", out, nbElem);
        invoke(() -> core.cdlIdentical3Crows(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlidentical3crows", out, nbElem);
        invoke(() -> core.cdlInNeck(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlinneck", out, nbElem);
        invoke(() -> core.cdlInvertedHammer(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlinvertedhammer", out, nbElem);
        invoke(() -> core.cdlKicking(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlkicking", out, nbElem);
        invoke(() -> core.cdlKickingByLength(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlkickingbylength", out, nbElem);
        invoke(() -> core.cdlLadderBottom(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlladderbottom", out, nbElem);
        invoke(() -> core.cdlLongLeggedDoji(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdllongleggeddoji", out, nbElem);
        invoke(() -> core.cdlLongLine(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdllongline", out, nbElem);
        invoke(() -> core.cdlMarubozu(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlmarubozu", out, nbElem);
        invoke(() -> core.cdlMatchingLow(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlmatchinglow", out, nbElem);
        invoke(() -> core.cdlMatHold(0, n - 1, opens, highs, lows, closes, 0.5, begIdx, nbElem, out),
                record, "cdlmathold", out, nbElem);
        invoke(() -> core.cdlMorningDojiStar(0, n - 1, opens, highs, lows, closes, 0.3, begIdx, nbElem, out),
                record, "cdlmorningdojistar", out, nbElem);
        invoke(() -> core.cdlMorningStar(0, n - 1, opens, highs, lows, closes, 0.3, begIdx, nbElem, out),
                record, "cdlmorningstar", out, nbElem);
        invoke(() -> core.cdlOnNeck(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlonneck", out, nbElem);
        invoke(() -> core.cdlPiercing(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlpiercing", out, nbElem);
        invoke(() -> core.cdlRickshawMan(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlrickshawman", out, nbElem);
        invoke(() -> core.cdlRiseFall3Methods(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlrisefall3methods", out, nbElem);
        invoke(() -> core.cdlSeparatingLines(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlseparatinglines", out, nbElem);
        invoke(() -> core.cdlShootingStar(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlshootingstar", out, nbElem);
        invoke(() -> core.cdlShortLine(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlshortline", out, nbElem);
        invoke(() -> core.cdlSpinningTop(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlspinningtop", out, nbElem);
        invoke(() -> core.cdlStalledPattern(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlstalledpattern", out, nbElem);
        invoke(() -> core.cdlStickSandwhich(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlsticksandwich", out, nbElem);
        invoke(() -> core.cdlTakuri(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdltakuri", out, nbElem);
        invoke(() -> core.cdlTasukiGap(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdltasukigap", out, nbElem);
        invoke(() -> core.cdlThrusting(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlthrusting", out, nbElem);
        invoke(() -> core.cdlTristar(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdltristar", out, nbElem);
        invoke(() -> core.cdlUnique3River(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlunique3river", out, nbElem);
        invoke(() -> core.cdlUpsideGap2Crows(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlupsidegap2crows", out, nbElem);
        invoke(() -> core.cdlXSideGap3Methods(0, n - 1, opens, highs, lows, closes, begIdx, nbElem, out),
                record, "cdlxsidegap3methods", out, nbElem);
    }

    @FunctionalInterface
    private interface PatternCall {
        RetCode run() throws Exception;
    }

    private void invoke(PatternCall call, IndicatorRecord record, String name, int[] out, MInteger nb) {
        try {
            RetCode rc = call.run();
            if (rc == RetCode.Success && nb.value > 0) {
                int value = out[nb.value - 1];
                if (value != 0) {
                    record.put(name, value);
                }
            }
        } catch (Exception ignored) {
            // insufficient lookback window
        }
    }
}
