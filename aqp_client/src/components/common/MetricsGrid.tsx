import { type ReactNode } from "react";

import { Numeric } from "@/components/common/Numeric";
import { cn } from "@/lib/utils";

export type MetricKind = "money" | "percent" | "decimal" | "integer";

export interface Metric {
  label: string;
  value: number | null | undefined;
  kind?: MetricKind;
  /** Forces a tone instead of sign-derived auto. */
  tone?: "auto" | "neutral" | "force-pos" | "force-neg";
  /** Force a leading sign on positive values. */
  signed?: boolean;
  /** Number of fraction digits. Defaults to 2 for decimal/percent/money,
   *  0 for integer. */
  digits?: number;
  /** Optional sub-line rendered under the value (e.g. "vs. last 30d"). */
  hint?: ReactNode;
}

interface MetricsGridProps {
  metrics: Metric[];
  /** Number of columns at the largest breakpoint. Defaults to 4. */
  columns?: 2 | 3 | 4 | 6 | 9;
  /** Smaller text variant for dense detail-page sidebars. */
  compact?: boolean;
  className?: string;
}

const COL_CLASSES: Record<NonNullable<MetricsGridProps["columns"]>, string> = {
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-2 lg:grid-cols-4",
  6: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-6",
  9: "grid-cols-3 sm:grid-cols-3 lg:grid-cols-9",
};

/**
 * Compact, sign-aware metrics grid. Used by every detail surface
 * (bot, backtest, RL run, portfolio). Each cell is built on `Numeric`
 * so semantic financial colours and tabular figures come for free.
 */
export function MetricsGrid({ metrics, columns = 4, compact = false, className }: MetricsGridProps) {
  return (
    <div className={cn("grid gap-2", COL_CLASSES[columns], className)}>
      {metrics.map((m, i) => (
        <div
          key={`${m.label}-${i}`}
          className={cn(
            "rounded-md border border-[var(--border-default)] bg-[var(--bg-surface)] p-3",
            compact && "p-2",
          )}
        >
          <div
            className={cn(
              "text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]",
              compact && "text-[9px]",
            )}
          >
            {m.label}
          </div>
          <Numeric
            value={m.value ?? null}
            kind={m.kind ?? "decimal"}
            digits={m.digits ?? defaultDigits(m.kind)}
            color={m.tone ?? "auto"}
            signed={m.signed ?? false}
            className={cn("font-semibold", compact ? "text-base" : "text-xl")}
          />
          {m.hint ? (
            <div className="mt-0.5 text-[10px] text-[var(--text-secondary)]">{m.hint}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function defaultDigits(kind: MetricKind | undefined): number {
  if (kind === "integer") return 0;
  return 2;
}
