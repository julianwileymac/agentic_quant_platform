import { History } from "lucide-react";

import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { Badge } from "@/components/ui/badge";

import { useStrategyDev } from "./StrategyDevContext";

/**
 * Persistent run-summary strip rendered at the top of every
 * `/strategy-development/*` sub-route. Reads the latest run summary from
 * `StrategyDevContext` so navigating between siblings keeps the strip
 * coherent without re-fetching anything. Concrete sub-routes are
 * responsible for calling `setSelection({ lastRunSummary, lastTaskId })`
 * when they receive terminal stream events.
 */
export function RunKpiStrip() {
  const { selection } = useStrategyDev();
  const summary = selection.lastRunSummary;

  const metrics: Metric[] = [
    {
      label: "Sharpe",
      value: summary?.sharpe ?? null,
      kind: "decimal",
      digits: 3,
      tone: "auto",
    },
    {
      label: "Total return",
      value: summary?.totalReturn ?? null,
      kind: "percent",
      digits: 2,
      tone: "auto",
      signed: true,
    },
    {
      label: "Max DD",
      value: summary?.maxDrawdown ?? null,
      kind: "percent",
      digits: 2,
      tone: "auto",
    },
    {
      label: "Hit rate",
      value: summary?.hitRate ?? null,
      kind: "percent",
      digits: 1,
      tone: "neutral",
    },
    {
      label: "Trades",
      value: summary?.trades ?? null,
      kind: "integer",
      tone: "neutral",
    },
  ];

  if (!summary && !selection.lastTaskId) {
    return (
      <div className="flex items-center justify-between rounded-md border border-dashed border-[var(--border-subtle)] bg-[var(--bg-surface)]/40 px-3 py-2 text-xs text-[var(--text-secondary)]">
        <div className="flex items-center gap-2">
          <History className="h-3.5 w-3.5 opacity-70" />
          <span>No active run. Launch a backtest / batch / scenario to populate the strip.</span>
        </div>
        <Badge variant="outline">idle</Badge>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-[var(--border-default)] bg-[var(--bg-surface)] p-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs">
          <History className="h-3.5 w-3.5 opacity-70" />
          <span className="font-medium text-[var(--text-primary)]">
            {summary?.kind?.replace("_", " ") ?? "task"} ·
          </span>
          <code className="rounded bg-[var(--bg-app)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-secondary)]">
            {summary?.runId ?? selection.lastTaskId ?? "—"}
          </code>
          {summary?.at ? (
            <span className="text-[10px] text-[var(--text-secondary)]">{summary.at}</span>
          ) : null}
        </div>
        {summary ? (
          <Badge variant="positive">complete</Badge>
        ) : (
          <Badge variant="default">running</Badge>
        )}
      </div>
      <MetricsGrid metrics={metrics} columns={6} compact />
    </div>
  );
}
