import { Loader2, Play } from "lucide-react";
import { useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { DeploymentPicker } from "@/components/strategy-dev/DeploymentPicker";
import { useStrategyDev } from "@/components/strategy-dev/StrategyDevLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

interface PredictResponse {
  prediction: number;
}

/**
 * Single-row prediction harness. Wraps `POST /ml/test/single`. Shares
 * deployment + feature row state with the rest of the strategy-dev
 * umbrella via {@link useStrategyDev}.
 */
export function SinglePredictRoute() {
  const { selection, setSelection } = useStrategyDev();
  const [busy, setBusy] = useState(false);
  const [prediction, setPrediction] = useState<number | null>(null);

  const run = async () => {
    if (!selection.deploymentId) {
      toast.warning("Pick a deployment first");
      return;
    }
    let row: Record<string, number>;
    try {
      const parsed = JSON.parse(selection.featureRowText || "{}") as Record<string, unknown>;
      row = {};
      for (const [k, v] of Object.entries(parsed)) {
        const n = typeof v === "number" ? v : Number(v);
        if (Number.isFinite(n)) row[k] = n;
      }
    } catch (err) {
      toast.error(`Invalid JSON: ${(err as Error).message}`);
      return;
    }
    setBusy(true);
    setPrediction(null);
    try {
      const res = await apiFetch<PredictResponse>("/ml/test/single", {
        method: "POST",
        body: JSON.stringify({
          deployment_id: selection.deploymentId,
          feature_row: row,
          sync: true,
        }),
      });
      setPrediction(res.prediction);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Single-row inference</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <DeploymentPicker
            label="Deployment"
            value={selection.deploymentId}
            onChange={(deploymentId) => setSelection({ deploymentId })}
          />
          <div className="space-y-1">
            <label className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">
              Feature row (JSON)
            </label>
            <div className="h-40 overflow-hidden rounded-md">
              <CodeEditor
                language="json"
                value={selection.featureRowText}
                onChange={(featureRowText) => setSelection({ featureRowText })}
              />
            </div>
          </div>
          <Button onClick={run} disabled={busy || !selection.deploymentId}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Predict
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Prediction</CardTitle>
        </CardHeader>
        <CardContent>
          {prediction === null ? (
            <p className="text-xs text-[var(--text-secondary)]">
              Submit a row to score.
            </p>
          ) : (
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)]">Score</span>
                <span className="font-mono font-semibold">{prediction.toFixed(6)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)]">Sign</span>
                <Badge variant={prediction >= 0 ? "positive" : "negative"}>
                  {prediction >= 0 ? "long bias" : "short bias"}
                </Badge>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
