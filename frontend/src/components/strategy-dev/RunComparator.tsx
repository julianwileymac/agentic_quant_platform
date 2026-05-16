import { GitCompare, Loader2, Plus, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

import { DeploymentPicker } from "./DeploymentPicker";
import { useStrategyDev } from "./StrategyDevLayout";
import { SymbolsInput } from "./SymbolsInput";

interface PairwiseResp {
  task_id: string;
}

interface CompareSlot {
  deploymentId: string;
  taskId?: string;
}

/**
 * N-deep comparator. The backend `/ml/test/compare` is pairwise only —
 * we chain N-1 calls and surface each pairwise task id in the UI so the
 * caller can review them downstream.
 */
export function RunComparator() {
  const { selection, setSelection } = useStrategyDev();
  const [slots, setSlots] = useState<CompareSlot[]>([
    { deploymentId: selection.deploymentId },
    { deploymentId: selection.deploymentIdB ?? "" },
  ]);
  const [submitting, setSubmitting] = useState(false);

  const addSlot = () => setSlots((cur) => [...cur, { deploymentId: "" }]);
  const removeSlot = (i: number) => setSlots((cur) => cur.filter((_, idx) => idx !== i));

  const updateSlot = (i: number, deploymentId: string) =>
    setSlots((cur) => cur.map((s, idx) => (idx === i ? { ...s, deploymentId } : s)));

  const launch = async () => {
    const filled = slots.filter((s) => s.deploymentId);
    if (filled.length < 2) {
      toast.warning("Pick at least two deployments");
      return;
    }
    if (new Set(filled.map((s) => s.deploymentId)).size !== filled.length) {
      toast.warning("Pick distinct deployments per slot");
      return;
    }
    setSubmitting(true);
    const taskedSlots: CompareSlot[] = [...filled];
    try {
      for (let i = 1; i < filled.length; i++) {
        const res = await apiFetch<PairwiseResp>("/ml/test/compare", {
          method: "POST",
          body: JSON.stringify({
            deployment_id_a: filled[0]!.deploymentId,
            deployment_id_b: filled[i]!.deploymentId,
            symbols: selection.symbols,
            start: selection.start,
            end: selection.end,
            last_n: 200,
          }),
        });
        taskedSlots[i] = { deploymentId: filled[i]!.deploymentId, taskId: res.task_id };
      }
      setSlots(taskedSlots);
      const firstTask = taskedSlots[1]?.taskId;
      if (firstTask) setSelection({ lastTaskId: firstTask });
      toast.success(`Launched ${filled.length - 1} pairwise comparisons`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>N-deep comparison</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-[var(--text-secondary)]">
            Backend compare endpoint is strictly pairwise — slot #0 acts as the anchor; we run
            anchor↔slot-i for i ≥ 1. Each comparison becomes its own Celery task.
          </p>
          <div className="space-y-2">
            {slots.map((slot, i) => (
              <div key={i} className="flex items-end gap-2">
                <div className="flex-1">
                  <DeploymentPicker
                    label={i === 0 ? "Anchor deployment" : `Comparison ${i}`}
                    value={slot.deploymentId}
                    onChange={(d) => updateSlot(i, d)}
                  />
                </div>
                {i > 1 ? (
                  <Button variant="ghost" size="icon" onClick={() => removeSlot(i)}>
                    <X className="h-4 w-4" />
                  </Button>
                ) : null}
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={addSlot}>
              <Plus className="h-3.5 w-3.5" />
              Add deployment
            </Button>
          </div>
          <SymbolsInput
            label="Symbols"
            value={selection.symbols}
            onChange={(symbols) => setSelection({ symbols })}
          />
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Start</Label>
              <input
                value={selection.start}
                onChange={(e) => setSelection({ start: e.target.value })}
                className="h-9 w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label>End</Label>
              <input
                value={selection.end}
                onChange={(e) => setSelection({ end: e.target.value })}
                className="h-9 w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
              />
            </div>
          </div>
          <Button onClick={launch} disabled={submitting}>
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitCompare className="h-4 w-4" />}
            Run pairwise sweep
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Pairwise tasks</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-2 text-xs">
            {slots.slice(1).map((s, i) => (
              <li
                key={`${s.deploymentId}-${i}`}
                className="flex items-center justify-between rounded-md border border-[var(--border-default)] p-2"
              >
                <span className="font-mono">
                  {slots[0]!.deploymentId.slice(0, 8)} ↔ {s.deploymentId.slice(0, 8) || "?"}
                </span>
                {s.taskId ? (
                  <Badge variant="default" className="font-mono text-[10px]">
                    {s.taskId.slice(0, 8)}…
                  </Badge>
                ) : (
                  <Badge variant="outline">pending</Badge>
                )}
              </li>
            ))}
            {slots.length <= 1 ? (
              <li className="text-[var(--text-secondary)]">No pairwise comparisons yet.</li>
            ) : null}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
