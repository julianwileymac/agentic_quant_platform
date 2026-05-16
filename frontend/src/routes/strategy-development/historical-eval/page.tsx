import { FlaskConical, Loader2 } from "lucide-react";
import { useState } from "react";

import { StreamLog } from "@/components/strategy-dev/StreamLog";
import { useStrategyDev } from "@/components/strategy-dev/StrategyDevLayout";
import { SymbolsInput } from "@/components/strategy-dev/SymbolsInput";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

interface ModelRow {
  id: string;
  registry_name?: string | null;
  algo?: string | null;
}

interface SplitPlanRow {
  id: string;
  name: string;
  method: string;
}

interface EvalResp {
  task_id: string;
}

interface EvaluationDetail {
  task_id: string;
  metrics?: Record<string, number>;
  status?: string;
  mlflow_run_id?: string | null;
}

/**
 * Historical evaluation tab. Reuses the existing `POST /ml/evaluate`
 * surface; supports either a saved `split_plan_id` or an ad-hoc
 * symbols/start/end DatasetH config.
 */
export function HistoricalEvalRoute() {
  const { selection, setSelection } = useStrategyDev();
  const [registryName, setRegistryName] = useState("");
  const [splitPlanId, setSplitPlanId] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const models = useApiQuery<ModelRow[]>({
    queryKey: ["ml", "models"],
    path: "/ml/models",
    select: (raw) => (Array.isArray(raw) ? (raw as ModelRow[]) : []),
  });
  const splits = useApiQuery<SplitPlanRow[]>({
    queryKey: ["ml", "split-plans"],
    path: "/ml/split-plans",
    select: (raw) => (Array.isArray(raw) ? (raw as SplitPlanRow[]) : []),
  });
  const evalDetail = useApiQuery<EvaluationDetail>({
    queryKey: ["ml", "evaluation", selection.lastTaskId ?? ""],
    path: `/ml/evaluations/${selection.lastTaskId ?? ""}`,
    enabled: Boolean(selection.lastTaskId),
    refetchInterval: 4_000,
  });

  const launch = async () => {
    if (!registryName) {
      toast.warning("Pick a model first");
      return;
    }
    const body: Record<string, unknown> = { registry_name: registryName };
    if (splitPlanId) {
      body.dataset_cfg = { split_plan_id: splitPlanId };
    } else {
      body.dataset_cfg = {
        class: "DatasetH",
        module_path: "aqp.ml.dataset",
        kwargs: {
          handler: {
            class: "Alpha158",
            module_path: "aqp.ml.features.alpha158",
            kwargs: {
              instruments: selection.symbols,
              start_time: selection.start,
              end_time: selection.end,
            },
          },
          segments: { test: [selection.start, selection.end] },
        },
      };
    }
    setSubmitting(true);
    try {
      const res = await apiFetch<EvalResp>("/ml/evaluate", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSelection({ lastTaskId: res.task_id, lastRunSummary: null });
      toast.success(`Evaluation queued (${res.task_id.slice(0, 8)}…)`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const metricItems = Object.entries(evalDetail.data?.metrics ?? {});

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Evaluate</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="hist-model">Model</Label>
            <select
              id="hist-model"
              className="h-9 w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
              value={registryName}
              onChange={(e) => setRegistryName(e.target.value)}
            >
              <option value="">Pick a registered model</option>
              {(models.data ?? []).map((m) => (
                <option key={m.id} value={m.registry_name ?? m.id}>
                  {m.registry_name ?? m.id}
                  {m.algo ? ` · ${m.algo}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="hist-split">Split plan (optional)</Label>
            <select
              id="hist-split"
              className="h-9 w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
              value={splitPlanId}
              onChange={(e) => setSplitPlanId(e.target.value)}
            >
              <option value="">Use ad-hoc dataset config</option>
              {(splits.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.method})
                </option>
              ))}
            </select>
          </div>
          {!splitPlanId ? (
            <>
              <SymbolsInput
                label="Symbols"
                value={selection.symbols}
                onChange={(symbols) => setSelection({ symbols })}
              />
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="hist-start">Start</Label>
                  <Input
                    id="hist-start"
                    value={selection.start}
                    onChange={(e) => setSelection({ start: e.target.value })}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="hist-end">End</Label>
                  <Input
                    id="hist-end"
                    value={selection.end}
                    onChange={(e) => setSelection({ end: e.target.value })}
                  />
                </div>
              </div>
            </>
          ) : null}
          <Button onClick={launch} disabled={submitting || !registryName}>
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FlaskConical className="h-4 w-4" />
            )}
            Run evaluate
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Run output</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <StreamLog taskId={selection.lastTaskId ?? null} maxHeight={200} />
          {metricItems.length ? (
            <div className="rounded-md border border-[var(--border-default)] p-2">
              <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">
                MLflow metrics
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {metricItems.map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-2">
                    <span className="text-[var(--text-secondary)]">{k}</span>
                    <span className="font-mono">{typeof v === "number" ? v.toFixed(4) : String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
