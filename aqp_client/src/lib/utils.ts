import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn-style class-name composition helper. Combines `clsx` for
 * conditional logic with `tailwind-merge` so duplicate / conflicting
 * tailwind utilities are reconciled in a deterministic order.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format a number with locale-aware grouping and a fixed precision.
 * Always produces tabular widths because the consumer renders inside
 * a `tabular`-classed container (see {@link Numeric}).
 */
export function formatNumber(
  value: number,
  options: Intl.NumberFormatOptions = {},
  locale = "en-US",
): string {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    ...options,
  }).format(value);
}

/**
 * Format a percentage with a leading sign so the colour-coded
 * Numeric component never has to disambiguate.
 */
export function formatPercent(value: number, fractionDigits = 2): string {
  if (!Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(fractionDigits)}%`;
}

/**
 * Format an ISO timestamp to short HH:mm:ss for live trading rows.
 */
export function formatTime(iso: string | number): string {
  try {
    const d = typeof iso === "string" ? new Date(iso) : new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleTimeString(undefined, { hour12: false });
  } catch {
    return "—";
  }
}
