/**
 * lightweight-charts v4 primitive implementations for every
 * ``LAB_LABEL_KINDS`` value declared in
 * :mod:`aqp.persistence.models_lab`. Each primitive implements
 * ``ISeriesPrimitive`` so it attaches to a chart series via
 * ``series.attachPrimitive(...)``.
 *
 * Phase 5 ships these as small standalone classes so the
 * SimulationPanel + a future Labeling panel can drop them onto an
 * OHLC chart without forking the chart wrapper. CRUD against the
 * backend goes through the existing ``/lab/labels`` API client.
 *
 * Implementation notes:
 *
 * - lightweight-charts v4's ``ISeriesPrimitive`` API has been the
 *   stable extension surface since v4.0; v5's API is a superset but
 *   the v4 surface is what aqp_client currently pins.
 * - All primitives draw with the canvas 2D context — no DOM nodes.
 *   This keeps repaint cost bounded even with hundreds of labels.
 * - Hit-testing for click / hover is intentionally simple
 *   (rectangle-based) — the drawing toolbar handles fine-grained
 *   selection via the canvas overlay above the chart.
 */
import type {
  IChartApi,
  ISeriesApi,
  ISeriesPrimitive,
  ISeriesPrimitivePaneView,
  ISeriesPrimitivePaneRenderer,
  SeriesType,
  Time,
} from "lightweight-charts";

export type LabLabelKind =
  | "support_resistance"
  | "trendline"
  | "swing"
  | "regime_band"
  | "pattern"
  | "order_event"
  | "annotation";

export interface LabAnnotation<TPayload = Record<string, unknown>> {
  id: string;
  vt_symbol: string;
  kind: LabLabelKind;
  t_start: number; // unix seconds (lightweight-charts Time)
  t_end?: number | null;
  payload: TPayload;
}

interface PrimitiveContext {
  chart: IChartApi;
  series: ISeriesApi<SeriesType>;
}

// ---------------------------------------------------------------------------
// SupportResistancePrimitive
// ---------------------------------------------------------------------------

interface SupportResistancePayload {
  price: number;
  label?: string;
  color?: string;
}

export class SupportResistancePrimitive
  implements ISeriesPrimitive<Time>
{
  constructor(
    private readonly annotation: LabAnnotation<SupportResistancePayload>,
    private readonly ctx: PrimitiveContext,
  ) {}

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    const annotation = this.annotation;
    const ctx = this.ctx;
    return [
      {
        renderer: (): ISeriesPrimitivePaneRenderer => ({
          draw: (target) => {
            const price = annotation.payload.price;
            const y = ctx.series.priceToCoordinate(price);
            if (y == null) return;
            target.useBitmapCoordinateSpace(({ context, bitmapSize }) => {
              context.save();
              context.strokeStyle = annotation.payload.color ?? "#0ea5e9";
              context.lineWidth = 1;
              context.setLineDash([6, 4]);
              context.beginPath();
              context.moveTo(0, y);
              context.lineTo(bitmapSize.width, y);
              context.stroke();
              if (annotation.payload.label) {
                context.fillStyle = annotation.payload.color ?? "#0ea5e9";
                context.font = "11px ui-monospace";
                context.fillText(annotation.payload.label, 6, y - 4);
              }
              context.restore();
            });
          },
        }),
      },
    ];
  }
}

// ---------------------------------------------------------------------------
// TrendlinePrimitive
// ---------------------------------------------------------------------------

interface TrendlinePayload {
  p1_time: number;
  p1_price: number;
  p2_time: number;
  p2_price: number;
  color?: string;
}

export class TrendlinePrimitive implements ISeriesPrimitive<Time> {
  constructor(
    private readonly annotation: LabAnnotation<TrendlinePayload>,
    private readonly ctx: PrimitiveContext,
  ) {}

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    const annotation = this.annotation;
    const ctx = this.ctx;
    return [
      {
        renderer: (): ISeriesPrimitivePaneRenderer => ({
          draw: (target) => {
            const p1x = ctx.chart.timeScale().timeToCoordinate(
              annotation.payload.p1_time as Time,
            );
            const p2x = ctx.chart.timeScale().timeToCoordinate(
              annotation.payload.p2_time as Time,
            );
            const p1y = ctx.series.priceToCoordinate(annotation.payload.p1_price);
            const p2y = ctx.series.priceToCoordinate(annotation.payload.p2_price);
            if (p1x == null || p2x == null || p1y == null || p2y == null) return;
            target.useBitmapCoordinateSpace(({ context }) => {
              context.save();
              context.strokeStyle = annotation.payload.color ?? "#a78bfa";
              context.lineWidth = 1.5;
              context.beginPath();
              context.moveTo(p1x, p1y);
              context.lineTo(p2x, p2y);
              context.stroke();
              context.restore();
            });
          },
        }),
      },
    ];
  }
}

// ---------------------------------------------------------------------------
// SwingPointPrimitive — triangle markers above / below bars
// ---------------------------------------------------------------------------

interface SwingPayload {
  price: number;
  direction: "high" | "low";
  color?: string;
}

export class SwingPointPrimitive implements ISeriesPrimitive<Time> {
  constructor(
    private readonly annotation: LabAnnotation<SwingPayload>,
    private readonly ctx: PrimitiveContext,
  ) {}

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    const annotation = this.annotation;
    const ctx = this.ctx;
    return [
      {
        renderer: (): ISeriesPrimitivePaneRenderer => ({
          draw: (target) => {
            const x = ctx.chart.timeScale().timeToCoordinate(
              annotation.t_start as Time,
            );
            const y = ctx.series.priceToCoordinate(annotation.payload.price);
            if (x == null || y == null) return;
            target.useBitmapCoordinateSpace(({ context }) => {
              context.save();
              context.fillStyle = annotation.payload.color
                ?? (annotation.payload.direction === "high" ? "#10b981" : "#ef4444");
              context.beginPath();
              if (annotation.payload.direction === "high") {
                context.moveTo(x, y - 12);
                context.lineTo(x - 6, y - 4);
                context.lineTo(x + 6, y - 4);
              } else {
                context.moveTo(x, y + 12);
                context.lineTo(x - 6, y + 4);
                context.lineTo(x + 6, y + 4);
              }
              context.closePath();
              context.fill();
              context.restore();
            });
          },
        }),
      },
    ];
  }
}

// ---------------------------------------------------------------------------
// RegimeBandPrimitive — translucent rectangle over a time range
// ---------------------------------------------------------------------------

interface RegimeBandPayload {
  label: string;
  color?: string;
  alpha?: number;
}

export class RegimeBandPrimitive implements ISeriesPrimitive<Time> {
  constructor(
    private readonly annotation: LabAnnotation<RegimeBandPayload>,
    private readonly ctx: PrimitiveContext,
  ) {}

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    const annotation = this.annotation;
    const ctx = this.ctx;
    return [
      {
        zOrder: "bottom",
        renderer: (): ISeriesPrimitivePaneRenderer => ({
          draw: (target) => {
            if (annotation.t_end == null) return;
            const x1 = ctx.chart.timeScale().timeToCoordinate(annotation.t_start as Time);
            const x2 = ctx.chart.timeScale().timeToCoordinate(annotation.t_end as Time);
            if (x1 == null || x2 == null) return;
            const alpha = annotation.payload.alpha ?? 0.12;
            target.useBitmapCoordinateSpace(({ context, bitmapSize }) => {
              context.save();
              context.fillStyle = annotation.payload.color ?? "#f59e0b";
              context.globalAlpha = alpha;
              context.fillRect(Math.min(x1, x2), 0, Math.abs(x2 - x1), bitmapSize.height);
              context.globalAlpha = 1;
              context.fillStyle = annotation.payload.color ?? "#f59e0b";
              context.font = "10px ui-monospace";
              context.fillText(annotation.payload.label, Math.min(x1, x2) + 4, 14);
              context.restore();
            });
          },
        }),
      },
    ];
  }
}

// ---------------------------------------------------------------------------
// PatternPrimitive — polygon outline (H&S, triangle, flag, ...)
// ---------------------------------------------------------------------------

interface PatternPayload {
  points: Array<{ time: number; price: number }>;
  label?: string;
  color?: string;
}

export class PatternPrimitive implements ISeriesPrimitive<Time> {
  constructor(
    private readonly annotation: LabAnnotation<PatternPayload>,
    private readonly ctx: PrimitiveContext,
  ) {}

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    const annotation = this.annotation;
    const ctx = this.ctx;
    return [
      {
        renderer: (): ISeriesPrimitivePaneRenderer => ({
          draw: (target) => {
            const points = annotation.payload.points
              .map((p) => {
                const x = ctx.chart.timeScale().timeToCoordinate(p.time as Time);
                const y = ctx.series.priceToCoordinate(p.price);
                if (x == null || y == null) return null;
                return { x, y };
              })
              .filter((p): p is { x: number; y: number } => p !== null);
            if (points.length < 2) return;
            target.useBitmapCoordinateSpace(({ context }) => {
              context.save();
              context.strokeStyle = annotation.payload.color ?? "#ec4899";
              context.lineWidth = 1.5;
              context.beginPath();
              context.moveTo(points[0].x, points[0].y);
              for (let i = 1; i < points.length; i++) {
                context.lineTo(points[i].x, points[i].y);
              }
              context.stroke();
              if (annotation.payload.label) {
                context.fillStyle = annotation.payload.color ?? "#ec4899";
                context.font = "11px ui-monospace";
                context.fillText(annotation.payload.label, points[0].x + 6, points[0].y - 4);
              }
              context.restore();
            });
          },
        }),
      },
    ];
  }
}

// ---------------------------------------------------------------------------
// OrderEventMarker — buy / sell triangle + tooltip
// ---------------------------------------------------------------------------

interface OrderEventPayload {
  side: "buy" | "sell";
  price: number;
  size?: number;
  label?: string;
}

export class OrderEventMarker implements ISeriesPrimitive<Time> {
  constructor(
    private readonly annotation: LabAnnotation<OrderEventPayload>,
    private readonly ctx: PrimitiveContext,
  ) {}

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    const annotation = this.annotation;
    const ctx = this.ctx;
    return [
      {
        renderer: (): ISeriesPrimitivePaneRenderer => ({
          draw: (target) => {
            const x = ctx.chart.timeScale().timeToCoordinate(
              annotation.t_start as Time,
            );
            const y = ctx.series.priceToCoordinate(annotation.payload.price);
            if (x == null || y == null) return;
            const isBuy = annotation.payload.side === "buy";
            target.useBitmapCoordinateSpace(({ context }) => {
              context.save();
              context.fillStyle = isBuy ? "#10b981" : "#ef4444";
              context.strokeStyle = isBuy ? "#10b981" : "#ef4444";
              context.lineWidth = 1;
              context.beginPath();
              if (isBuy) {
                context.moveTo(x, y - 9);
                context.lineTo(x - 5, y - 1);
                context.lineTo(x + 5, y - 1);
              } else {
                context.moveTo(x, y + 9);
                context.lineTo(x - 5, y + 1);
                context.lineTo(x + 5, y + 1);
              }
              context.closePath();
              context.fill();
              if (annotation.payload.label) {
                context.fillStyle = isBuy ? "#10b981" : "#ef4444";
                context.font = "10px ui-monospace";
                context.fillText(annotation.payload.label, x + 8, y);
              }
              context.restore();
            });
          },
        }),
      },
    ];
  }
}

// ---------------------------------------------------------------------------
// Factory — pick the right primitive class for a LabLabelKind
// ---------------------------------------------------------------------------

export function makeAnnotationPrimitive(
  annotation: LabAnnotation,
  ctx: PrimitiveContext,
): ISeriesPrimitive<Time> | null {
  switch (annotation.kind) {
    case "support_resistance":
      return new SupportResistancePrimitive(
        annotation as LabAnnotation<SupportResistancePayload>,
        ctx,
      );
    case "trendline":
      return new TrendlinePrimitive(
        annotation as LabAnnotation<TrendlinePayload>,
        ctx,
      );
    case "swing":
      return new SwingPointPrimitive(
        annotation as LabAnnotation<SwingPayload>,
        ctx,
      );
    case "regime_band":
      return new RegimeBandPrimitive(
        annotation as LabAnnotation<RegimeBandPayload>,
        ctx,
      );
    case "pattern":
      return new PatternPrimitive(
        annotation as LabAnnotation<PatternPayload>,
        ctx,
      );
    case "order_event":
      return new OrderEventMarker(
        annotation as LabAnnotation<OrderEventPayload>,
        ctx,
      );
    case "annotation":
      // Generic free-form text — render as a SupportResistance-style
      // dashed line when ``payload.price`` is present, otherwise no-op.
      if (
        typeof (annotation.payload as Record<string, unknown>).price === "number"
      ) {
        return new SupportResistancePrimitive(
          annotation as LabAnnotation<SupportResistancePayload>,
          ctx,
        );
      }
      return null;
    default:
      return null;
  }
}
