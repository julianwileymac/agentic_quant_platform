package io.rpi.flink.sample;

import java.io.Serializable;
import java.util.Objects;

/**
 * POJO mirroring {@code market_bar_v1} Avro schema. Flink's POJO serializer
 * picks up the public fields + no-args constructor automatically.
 */
public class MarketBar implements Serializable {

    private static final long serialVersionUID = 1L;

    public long tsNs;
    public String vtSymbol;
    public double open;
    public double high;
    public double low;
    public double close;
    public double volume;

    public MarketBar() {
    }

    public MarketBar(long tsNs, String vtSymbol, double open, double high, double low, double close, double volume) {
        this.tsNs = tsNs;
        this.vtSymbol = vtSymbol;
        this.open = open;
        this.high = high;
        this.low = low;
        this.close = close;
        this.volume = volume;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof MarketBar)) return false;
        MarketBar that = (MarketBar) o;
        return tsNs == that.tsNs && Double.compare(that.open, open) == 0
                && Double.compare(that.high, high) == 0 && Double.compare(that.low, low) == 0
                && Double.compare(that.close, close) == 0 && Double.compare(that.volume, volume) == 0
                && Objects.equals(vtSymbol, that.vtSymbol);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tsNs, vtSymbol, open, high, low, close, volume);
    }

    @Override
    public String toString() {
        return "MarketBar{" + vtSymbol + " @ " + tsNs + " c=" + close + "}";
    }
}
