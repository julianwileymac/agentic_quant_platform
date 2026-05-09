import { type CSSProperties, type HTMLAttributes, useMemo } from "react";

import { formatNumber, formatPercent } from "@/lib/utils";

type NumericKind = "money" | "percent" | "decimal" | "integer";
type ColorMode = "auto" | "neutral" | "force-pos" | "force-neg";

interface NumericProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  value: number | null | undefined;
  /** Pre-formatted text override (skips formatter). */
  text?: string;
  kind?: NumericKind;
  /**
   * `auto` colours by sign (negative -> red, positive -> green). `neutral`
   * keeps the inherited colour. `force-*` overrides for diff cells.
   */
  color?: ColorMode;
  /** Number of fraction digits shown. Defaults to 2. */
  digits?: number;
  /** Currency formatter override (USD by default for money kind). */
  currency?: string;
  /** Optional prefix (e.g. "$"). Skipped for money/percent kinds. */
  prefix?: string;
  /** Optional suffix (e.g. " USD"). */
  suffix?: string;
  /** Render zero in the neutral colour even when `auto`. Defaults to true. */
  treatZeroAsNeutral?: boolean;
  /** Force a leading sign for positive numbers (`+1.23`). */
  signed?: boolean;
}

/**
 * Numeric primitive used for every display of currency, P&L, percentages,
 * latencies, sizes, etc. Always renders inside a `tabular`-classed span so
 * digits keep identical column widths under fast updates and never cause
 * the surrounding layout to re-flow when the underlying number changes
 * (Bloomberg-terminal physiological-stability requirement).
 */
export function Numeric({
  value,
  text,
  kind = "decimal",
  color = "auto",
  digits = 2,
  currency = "USD",
  prefix,
  suffix,
  treatZeroAsNeutral = true,
  signed = false,
  className,
  style,
  ...rest
}: NumericProps) {
  const formatted = useMemo(() => {
    if (text != null) return text;
    if (value == null || !Number.isFinite(value)) return "—";

    switch (kind) {
      case "money":
        return formatNumber(value, {
          style: "currency",
          currency,
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
          signDisplay: signed ? "exceptZero" : "auto",
        });
      case "percent":
        return formatPercent(value, digits);
      case "integer":
        return formatNumber(value, {
          minimumFractionDigits: 0,
          maximumFractionDigits: 0,
          signDisplay: signed ? "exceptZero" : "auto",
        });
      case "decimal":
      default: {
        const formattedValue = formatNumber(value, {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
          signDisplay: signed ? "exceptZero" : "auto",
        });
        return formattedValue;
      }
    }
  }, [text, value, kind, digits, currency, signed]);

  const tone = useMemo<NumericKind extends never ? never : string>(() => {
    if (color === "neutral") return "var(--text-primary)";
    if (color === "force-pos") return "var(--pos-fg)";
    if (color === "force-neg") return "var(--neg-fg)";
    if (value == null || !Number.isFinite(value)) return "var(--text-secondary)";
    if (treatZeroAsNeutral && value === 0) return "var(--text-primary)";
    return value < 0 ? "var(--neg-fg)" : value > 0 ? "var(--pos-fg)" : "var(--text-primary)";
  }, [color, value, treatZeroAsNeutral]);

  const composedStyle: CSSProperties = {
    color: tone,
    fontVariantNumeric: "tabular-nums",
    fontFeatureSettings: '"tnum" 1',
    ...style,
  };

  return (
    <span
      data-numeric="true"
      className={className}
      style={composedStyle}
      {...rest}
    >
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}
