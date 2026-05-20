import { GitCompare, Loader2 } from "lucide-react";
import { useState } from "react";

import { DeploymentPicker } from "@/components/strategy-dev/DeploymentPicker";
import { StreamLog } from "@/components/strategy-dev/StreamLog";
import { useStrategyDev } from "@/components/strategy-dev/StrategyDevLayout";
import { SymbolsInput } from "@/components/strategy-dev/SymbolsInput";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

interface CompareResponse {
  task_id: string;
}

/**
 * Pairwise A/B model comparison. Calls `POST /ml/test/compare`. The
 * route comparator (see `RunComparator`) handles >2 deployments by
 * chaining N-1 pairwise calls.
 */
export function CompareModelsRoute() {
  const { selection, setSelection } = useStrategyDev();
  const [submitting, setSubmitting] = useState(false);

  const launch = async () => {
    if (!selection.deploymentId || !selection.deploymentIdB) {
      toast.warning("Pick both deployments first");
      return;
    }
    if (selection.deploymentId === selection.deploymentIdB) {
      toast.warning("Pick two different deployments");
      return;
    }
    setSubmitting(true);
    try {
      const res = await apiFetch<CompareResponse>("/ml/test/compare", {
        method: "POST",
        body: JSON.stringify({
          deployment_id_a: selection.deploymentId,
          deployment_id_b: selection.deploymentIdB,
          symbols: selection.symbols,
          start: selection.start,
          end: selection.end,
          last_n: 200,
        }),
      });
      setSelection({ lastTaskId: res.task_id, lastRunSummary: null });
      toast.success(`Comparison queued (${res.task_id.slice(0, 8)}…)`);
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
          <CardTitle>A/B compare two deployments</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <DeploymentPicker
            label="Deployment A"
            value={selection.deploymentId}
            onChange={(deploymentId) => setSelection({ deploymentId })}
            exclude={selection.deploymentIdB ?? null}
          />
          <DeploymentPicker
            label="Deployment B"
            value={selection.deploymentIdB ?? ""}
            onChange={(deploymentIdB) => setSelection({ deploymentIdB })}
            exclude={selection.deploymentId || null}
          />
          <SymbolsInput
            label="Symbols"
            value={selection.symbols}
            onChange={(symbols) => setSelection({ symbols })}
          />
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="cmp-start">Start</Label>
              <Input
                id="cmp-start"
                value={selection.start}
                onChange={(e) => setSelection({ start: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="cmp-end">End</Label>
              <Input
                id="cmp-end"
                value={selection.end}
                onChange={(e) => setSelection({ end: e.target.value })}
              />
            </div>
          </div>
          <Button
            onClick={launch}
            disabled={submitting || !selection.deploymentId || !selection.deploymentIdB}
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <GitCompare className="h-4 w-4" />
            )}
            Compare
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Output</CardTitle>
        </CardHeader>
        <CardContent>
          <StreamLog taskId={selection.lastTaskId ?? null} maxHeight={400} />
        </CardContent>
      </Card>
    </div>
  );
}
