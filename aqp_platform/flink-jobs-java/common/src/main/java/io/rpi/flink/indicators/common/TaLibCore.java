package io.rpi.flink.indicators.common;

import com.tictactec.ta.lib.Core;
import com.tictactec.ta.lib.MInteger;

/**
 * Thread-local {@link Core} holder.
 *
 * <p>The TA-Lib Java port is not safe for concurrent use, but Flink's
 * {@code KeyedProcessFunction} instances are single-threaded per subtask,
 * so one {@link ThreadLocal#get()} per subtask is both safe and avoids
 * recreating the relatively expensive {@code Core}.</p>
 */
public final class TaLibCore {

    private static final ThreadLocal<Core> CORE = ThreadLocal.withInitial(Core::new);

    private TaLibCore() {
    }

    public static Core get() {
        return CORE.get();
    }

    public static MInteger outBegIdx() {
        return new MInteger();
    }

    public static MInteger outNbElement() {
        return new MInteger();
    }

    public static double[] closes(java.util.List<MarketBar> bars) {
        double[] out = new double[bars.size()];
        for (int i = 0; i < bars.size(); i++) {
            out[i] = bars.get(i).close;
        }
        return out;
    }

    public static double[] opens(java.util.List<MarketBar> bars) {
        double[] out = new double[bars.size()];
        for (int i = 0; i < bars.size(); i++) {
            out[i] = bars.get(i).open;
        }
        return out;
    }

    public static double[] highs(java.util.List<MarketBar> bars) {
        double[] out = new double[bars.size()];
        for (int i = 0; i < bars.size(); i++) {
            out[i] = bars.get(i).high;
        }
        return out;
    }

    public static double[] lows(java.util.List<MarketBar> bars) {
        double[] out = new double[bars.size()];
        for (int i = 0; i < bars.size(); i++) {
            out[i] = bars.get(i).low;
        }
        return out;
    }

    public static double[] volumes(java.util.List<MarketBar> bars) {
        double[] out = new double[bars.size()];
        for (int i = 0; i < bars.size(); i++) {
            out[i] = bars.get(i).volume;
        }
        return out;
    }

    /**
     * Fetches the last value written by a TA-Lib function, or NaN when the
     * lookback window was not satisfied.
     */
    public static double last(double[] out, MInteger outNbElement) {
        int n = outNbElement.value;
        return n > 0 ? out[n - 1] : Double.NaN;
    }
}
