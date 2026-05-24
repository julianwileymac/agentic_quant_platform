/**
 * Custom-series stubs for the Simulation panel's LOB heatmap +
 * footprint-bar visualisation. lightweight-charts v4's
 * ``ICustomSeriesPaneView`` interface lets us draw arbitrary
 * canvas content as a series; we use that to render:
 *
 * - ``LOBHeatmapSeries`` — depth ladder (price × time) coloured by
 *   resting size on each side of the book.
 * - ``FootprintBarSeries`` — per-tick volume profile inside each bar
 *   (Bid / Ask volume side-by-side).
 *
 * Phase 5 ships the data contract + pane-view scaffolding; the real
 * data wiring lands when the Simulation panel feeds LOB snapshots
 * through the same WS bus.
 */
import type {
  CustomData,
  ICustomSeriesPaneView,
  PaneRendererCustomData,
  PriceToCoordinateConverter,
  Time,
} from "lightweight-charts";

export interface LOBHeatmapDataPoint extends CustomData<Time> {
  time: Time;
  /**
   * Sparse depth ladder — for each (price, side) pair this lists
   * the resting size. We use a sparse list to keep the wire frame
   * bounded for L3 books where most price levels are empty.
   */
  levels: Array<{ price: number; side: "bid" | "ask"; size: number }>;
}

export interface FootprintBarDataPoint extends CustomData<Time> {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
  /** Per-tick volume bucket: { price → {bidVolume, askVolume} }. */
  buckets: Record<string, { bid: number; ask: number }>;
}

// ---------------------------------------------------------------------------
// LOB heatmap
// ---------------------------------------------------------------------------

export class LOBHeatmapSeries
  implements ICustomSeriesPaneView<Time, LOBHeatmapDataPoint>
{
  private readonly options = {
    cellHeightPx: 10,
    bidColor: "rgba(16,185,129,0.6)",
    askColor: "rgba(239,68,68,0.6)",
    maxBuckets: 64,
  };

  defaultOptions() {
    return {
      visible: true,
      priceLineVisible: false,
      lastValueVisible: false,
    };
  }

  priceValueBuilder(data: LOBHeatmapDataPoint): number[] {
    if (!data.levels.length) return [0];
    const prices = data.levels.map((l) => l.price);
    return [Math.min(...prices), Math.max(...prices), prices[0]];
  }

  isWhitespace(): boolean {
    return false;
  }

  renderer() {
    const options = this.options;
    return {
      draw(
        target: PaneRendererCustomData<Time, LOBHeatmapDataPoint>,
        priceToCoordinate: PriceToCoordinateConverter,
      ) {
        target.useBitmapCoordinateSpace(({ context }) => {
          for (const bar of target.bars) {
            const { x, originalData } = bar;
            const data = originalData;
            if (!data?.levels?.length) continue;
            const levels = data.levels.slice(0, options.maxBuckets);
            const maxSize = Math.max(...levels.map((l) => l.size), 1);
            for (const level of levels) {
              const y = priceToCoordinate(level.price);
              if (y == null) continue;
              const intensity = level.size / maxSize;
              context.fillStyle = level.side === "bid"
                ? options.bidColor.replace("0.6", String(0.2 + 0.5 * intensity))
                : options.askColor.replace("0.6", String(0.2 + 0.5 * intensity));
              context.fillRect(x - 4, y - options.cellHeightPx / 2, 8, options.cellHeightPx);
            }
          }
        });
      },
    };
  }
}

// ---------------------------------------------------------------------------
// Footprint bar
// ---------------------------------------------------------------------------

export class FootprintBarSeries
  implements ICustomSeriesPaneView<Time, FootprintBarDataPoint>
{
  private readonly options = {
    barWidthPx: 28,
    cellHeightPx: 11,
    bidColor: "rgba(16,185,129,0.85)",
    askColor: "rgba(239,68,68,0.85)",
    fontPx: 9,
  };

  defaultOptions() {
    return { visible: true, priceLineVisible: false, lastValueVisible: false };
  }

  priceValueBuilder(data: FootprintBarDataPoint): number[] {
    return [data.low, data.high, data.close];
  }

  isWhitespace(): boolean {
    return false;
  }

  renderer() {
    const options = this.options;
    return {
      draw(
        target: PaneRendererCustomData<Time, FootprintBarDataPoint>,
        priceToCoordinate: PriceToCoordinateConverter,
      ) {
        target.useBitmapCoordinateSpace(({ context }) => {
          context.save();
          context.font = `${options.fontPx}px ui-monospace`;
          context.textAlign = "center";
          for (const bar of target.bars) {
            const { x, originalData } = bar;
            const data = originalData;
            if (!data?.buckets) continue;
            const entries = Object.entries(data.buckets);
            for (const [priceStr, vols] of entries) {
              const price = Number(priceStr);
              if (!Number.isFinite(price)) continue;
              const y = priceToCoordinate(price);
              if (y == null) continue;
              const halfHeight = options.cellHeightPx / 2;
              context.fillStyle = options.bidColor;
              context.fillText(
                String(vols.bid),
                x - options.barWidthPx / 4,
                y + halfHeight - 1,
              );
              context.fillStyle = options.askColor;
              context.fillText(
                String(vols.ask),
                x + options.barWidthPx / 4,
                y + halfHeight - 1,
              );
            }
          }
          context.restore();
        });
      },
    };
  }
}
