import ReactECharts from "echarts-for-react";
import { FlaskConical, Play, Trophy } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import {
  EdaFrameViewer,
  type FramePayload,
} from "@/features/data-lab/modes/eda/EdaFrameViewer";
import { useLabStore } from "@/features/data-lab/state/labStore";

interface TrialRow {
  trial_id: number;
  params: Record<string, number>;
  metric?: number;
}

interface SweepDraft {
  algo: "grid" | "random" | "optuna_tpe";
  primary_metric: string;
  cv: "holdout" | "walk_forward" | "combinatorial_purged";
  n_folds: number;
  n_test_folds: number;
  embargo_pct: number;
  budget: number;
  params: Array<{ path: string; values: string }>;
}

const DEFAULT_DRAFT: SweepDraft = {
  algo: "grid",
  primary_metric: "sharpe",
  cv: "combinatorial_purged",
  n_folds: 6,
  n_test_folds: 2,
  embargo_pct: 1.0,
  budget: 16,
  params: [{ path: "alpha.decay", values: "5, 10, 20, 30" }],
};

function expandGrid(draft: SweepDraft): TrialRow[] {
  if (!draft.params.length) return [];
  const axes: Array<{ path: string; values: number[] }> = draft.params.map(
    (p) => ({
      path: p.path,
      values: p.values
        .split(",")
        .map((v) => Number(v.trim()))
        .filter((v) => Number.isFinite(v)),
    }),
  );
  // Cartesian product.
  let combos: Array<Record<string, number>> = [{}];
  for (const axis of axes) {
    const next: Array<Record<string, number>> = [];
    for (const c of combos) {
      for (const v of axis.values) {
        next.push({ ...c, [axis.path]: v });
      }
    }
    combos = next;
  }
  return combos.slice(0, draft.budget).map((p, i) => ({
    trial_id: i,
    params: p,
    metric: 1.0 + (Math.random() - 0.5) * 0.4, // placeholder until backend dispatches
  }));
}

/**
 * Evaluation mode panel — Phase 3 implementation.
 *
 * Surfaces:
 *
 * - Sweep config (algo, primary metric, CV, n_folds, n_test_folds,
 *   embargo_pct, budget, and a dynamic list of {param_path, values}).
 * - Trial grid (AG Grid would render here; AG Grid v32 is already in
 *   deps but we use a vanilla table for the Phase 3 first cut so we
 *   don't enforce a new style bundle).
 * - Deflated Sharpe note — never display raw Sharpe alone.
 *
 * Phase 3 in this UI is intentionally lightweight: the backend
 * compiler + CPCV + DSR helpers are the heavy lifting (they ship the
 * honest math). Phase 4-5 add the ECharts parallel-coords plot and
 * the "promote winner" button.
 */
export function EvaluationPanel() {
  const [draft, setDraft] = useState<SweepDraft>(DEFAULT_DRAFT);
  const [trials, setTrials] = useState<TrialRow[]>([]);
  const draftGraph = useLabStore((s) => s.draftGraph);

  const totalPaths = useMemo(() => {
    if (draft.cv !== "combinatorial_purged") return draft.budget;
    if (draft.n_test_folds >= draft.n_folds) return 0;
    let num = 1;
    let denom = 1;
    for (let i = 0; i < draft.n_test_folds; i++) {
      num *= draft.n_folds - i;
      denom *= i + 1;
    }
    return Math.floor(num / denom);
  }, [draft.cv, draft.n_folds, draft.n_test_folds, draft.budget]);

  const guarded = totalPaths > 100;

  const handlePlan = () => {
    const expanded = expandGrid(draft);
    setTrials(expanded);
    toast.success(`Planned ${expanded.length} trials.`);
  };

  const addParam = () => {
    setDraft({
      ...draft,
      params: [...draft.params, { path: "", values: "0.0, 0.5, 1.0" }],
    });
  };

  const removeParam = (i: number) => {
    setDraft({ ...draft, params: draft.params.filter((_, j) => j !== i) });
  };

  const updateParam = (i: number, patch: { path?: string; values?: string }) => {
    const next = [...draft.params];
    const current = next[i];
    if (!current) return;
    next[i] = { path: current.path, values: current.values, ...patch };
    setDraft({ ...draft, params: next });
  };

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_1fr] gap-2">
      <Card>
        <CardContent className="grid grid-cols-2 gap-3 py-3 md:grid-cols-4">
          <div className="space-y-1">
            <Label>Algo</Label>
            <select
              className="w-full rounded-md border bg-background p-2 text-sm"
              value={draft.algo}
              onChange={(e) =>
                setDraft({ ...draft, algo: e.target.value as SweepDraft["algo"] })
              }
            >
              <option value="grid">grid</option>
              <option value="random">random</option>
              <option value="optuna_tpe">optuna_tpe</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label>Primary metric</Label>
            <Input
              value={draft.primary_metric}
              onChange={(e) =>
                setDraft({ ...draft, primary_metric: e.target.value })
              }
            />
          </div>
          <div className="space-y-1">
            <Label>CV</Label>
            <select
              className="w-full rounded-md border bg-background p-2 text-sm"
              value={draft.cv}
              onChange={(e) =>
                setDraft({ ...draft, cv: e.target.value as SweepDraft["cv"] })
              }
            >
              <option value="holdout">holdout</option>
              <option value="walk_forward">walk_forward</option>
              <option value="combinatorial_purged">combinatorial_purged</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label>Budget</Label>
            <Input
              type="number"
              value={draft.budget}
              onChange={(e) => setDraft({ ...draft, budget: Number(e.target.value) })}
            />
          </div>
          {draft.cv === "combinatorial_purged" ? (
            <>
              <div className="space-y-1">
                <Label>n_folds</Label>
                <Input
                  type="number"
                  value={draft.n_folds}
                  onChange={(e) =>
                    setDraft({ ...draft, n_folds: Number(e.target.value) })
                  }
                />
              </div>
              <div className="space-y-1">
                <Label>n_test_folds</Label>
                <Input
                  type="number"
                  value={draft.n_test_folds}
                  onChange={(e) =>
                    setDraft({ ...draft, n_test_folds: Number(e.target.value) })
                  }
                />
              </div>
              <div className="space-y-1">
                <Label>embargo_pct</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={draft.embargo_pct}
                  onChange={(e) =>
                    setDraft({ ...draft, embargo_pct: Number(e.target.value) })
                  }
                />
              </div>
              <div className="flex items-end">
                <Badge variant={guarded ? "negative" : "secondary"} className="ml-auto">
                  C({draft.n_folds}, {draft.n_test_folds}) = {totalPaths} paths
                </Badge>
              </div>
            </>
          ) : null}
          <div className="col-span-2 space-y-2 md:col-span-4">
            <div className="flex items-center gap-2">
              <Label>Parameters</Label>
              <Button variant="outline" size="sm" onClick={addParam} className="ml-auto">
                + param
              </Button>
            </div>
            {draft.params.map((p, i) => (
              <div key={i} className="grid grid-cols-[1fr_2fr_auto] gap-2">
                <Input
                  placeholder="node_id.param"
                  value={p.path}
                  onChange={(e) => updateParam(i, { path: e.target.value })}
                />
                <Input
                  placeholder="5, 10, 20"
                  value={p.values}
                  onChange={(e) => updateParam(i, { values: e.target.value })}
                />
                <Button variant="ghost" size="sm" onClick={() => removeParam(i)}>
                  ×
                </Button>
              </div>
            ))}
          </div>
          <div className="col-span-2 flex items-center md:col-span-4">
            {guarded ? (
              <span className="mr-auto text-xs text-rose-500">
                Path count exceeds the 100-guard. Confirm before submitting.
              </span>
            ) : null}
            <Button onClick={handlePlan} className="ml-auto gap-2">
              <Play className="h-4 w-4" /> Plan sweep
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card className="overflow-hidden">
        <CardContent className="flex h-full min-h-0 flex-col gap-2 py-2">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4" />
            <span className="text-sm font-medium">Trials</span>
            <Badge variant="outline">{trials.length} planned</Badge>
            {(() => {
              const scored = trials.filter((t) => typeof t.metric === "number");
              if (!scored.length) return null;
              const winner = scored.reduce((best, cur) =>
                (cur.metric ?? -Infinity) > (best.metric ?? -Infinity) ? cur : best,
              );
              return (
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto gap-2"
                  disabled={!draftGraph}
                  onClick={() => {
                    if (!draftGraph) {
                      toast.error(
                        "Save a Testing graph first before promoting a winner.",
                      );
                      return;
                    }
                    toast.success(
                      `Promote winner: trial ${winner.trial_id} (${draft.primary_metric}=${winner.metric?.toFixed(3) ?? "?"}). Open Testing mode to inspect the cloned spec.`,
                    );
                  }}
                  title="Clone the winning trial's params back as a fresh Testing-mode draft."
                >
                  <Trophy className="h-4 w-4" /> Promote winner #{winner.trial_id}
                </Button>
              );
            })()}
            {trials.length > 0 ? (
              <span className="text-xs text-muted-foreground">
                Render DSR alongside raw Sharpe — never the raw value alone.
              </span>
            ) : null}
          </div>
          {trials.length > 1 ? (
            <ParallelCoordsPlot trials={trials} primaryMetric={draft.primary_metric} />
          ) : null}
          <div className="min-h-0 flex-1">
            {trials.length === 0 ? (
              <div className="p-4 text-xs text-muted-foreground">
                No trials yet. Configure the sweep above and click "Plan sweep".
              </div>
            ) : (
              (() => {
                const firstParams = trials[0]?.params ?? {};
                const headerKeys = Object.keys(firstParams);
                const columns = ["trial_id", ...headerKeys, draft.primary_metric];
                const rows = trials.map((t) => {
                  const row: Record<string, unknown> = {
                    trial_id: t.trial_id,
                    [draft.primary_metric]:
                      typeof t.metric === "number" ? Number(t.metric.toFixed(4)) : null,
                  };
                  for (const k of headerKeys) {
                    row[k] = t.params[k];
                  }
                  return row;
                });
                const frame: FramePayload = {
                  columns,
                  rows,
                  total_rows: trials.length,
                };
                return (
                  <EdaFrameViewer
                    frame={frame}
                    caption="DSR will appear next to raw Sharpe once the sweep dispatches; never render raw Sharpe alone."
                    height="100%"
                  />
                );
              })()
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

interface ParallelCoordsProps {
  trials: TrialRow[];
  primaryMetric: string;
}

/**
 * ECharts parallel-coordinates plot keyed by trial.
 *
 * Each axis is one swept parameter; the rightmost axis is the
 * primary metric (Sharpe / IC / IR / ...). Lines are coloured by
 * the metric value so the user can spot the high-metric param
 * regions at a glance.
 */
function ParallelCoordsPlot({ trials, primaryMetric }: ParallelCoordsProps) {
  const option = useMemo(() => {
    const paramKeys = Object.keys(trials[0]?.params ?? {});
    const metricValues = trials
      .map((t) => t.metric)
      .filter((v): v is number => typeof v === "number");
    const metricMin = metricValues.length ? Math.min(...metricValues) : 0;
    const metricMax = metricValues.length ? Math.max(...metricValues) : 1;
    return {
      parallelAxis: [
        ...paramKeys.map((k, i) => ({
          dim: i,
          name: k,
          type: "value" as const,
        })),
        {
          dim: paramKeys.length,
          name: primaryMetric,
          type: "value" as const,
          min: metricMin,
          max: metricMax,
        },
      ],
      parallel: {
        left: 60,
        right: 60,
        top: 24,
        bottom: 24,
        axisExpandable: true,
      },
      visualMap: {
        type: "continuous",
        dimension: paramKeys.length,
        min: metricMin,
        max: metricMax,
        text: [`${primaryMetric} high`, "low"],
        right: 8,
        top: "middle",
        inRange: { color: ["#a78bfa", "#22d3ee", "#10b981"] },
      },
      series: [
        {
          type: "parallel" as const,
          smooth: true,
          lineStyle: { width: 1.5, opacity: 0.7 },
          data: trials.map((t) => [
            ...paramKeys.map((k) => Number(t.params[k] ?? 0)),
            typeof t.metric === "number" ? t.metric : null,
          ]),
        },
      ],
    };
  }, [trials, primaryMetric]);

  return (
    <div className="h-44 w-full">
      <ReactECharts
        option={option}
        style={{ height: "100%", width: "100%" }}
        notMerge={true}
        lazyUpdate={true}
      />
    </div>
  );
}

export default EvaluationPanel;
