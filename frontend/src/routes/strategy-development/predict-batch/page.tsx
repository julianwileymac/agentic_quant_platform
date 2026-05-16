import { Loader2, PlayCircle, Upload as UploadIcon } from "lucide-react";
import { useRef, useState } from "react";

import { DeploymentPicker } from "@/components/strategy-dev/DeploymentPicker";
import { StreamLog } from "@/components/strategy-dev/StreamLog";
import { useStrategyDev } from "@/components/strategy-dev/StrategyDevLayout";
import { SymbolsInput } from "@/components/strategy-dev/SymbolsInput";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

interface BatchTaskResponse {
  task_id: string;
}

interface CsvSummary {
  n_rows: number;
  predictions_summary: { mean: number; std: number; min: number; max: number };
  rows: Array<Record<string, unknown>>;
}

/**
 * Iceberg-aware batch scoring. Calls `POST /ml/test/batch` with
 * symbols / start / end / `iceberg_identifier`. The backend task is
 * upgraded in this same diff to honor the iceberg identifier (was a
 * documented gap before).
 */
export function PredictBatchRoute() {
  const { selection, setSelection } = useStrategyDev();
  const [icebergId, setIcebergId] = useState("");
  const [lastN, setLastN] = useState(200);
  const [csvSummary, setCsvSummary] = useState<CsvSummary | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const launchBatch = async () => {
    if (!selection.deploymentId) {
      toast.warning("Pick a deployment first");
      return;
    }
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        deployment_id: selection.deploymentId,
        symbols: selection.symbols,
        start: selection.start,
        end: selection.end,
        last_n: lastN,
      };
      if (icebergId.trim()) body.iceberg_identifier = icebergId.trim();
      const res = await apiFetch<BatchTaskResponse>("/ml/test/batch", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSelection({ lastTaskId: res.task_id, lastRunSummary: null });
      toast.success(`Batch queued (${res.task_id.slice(0, 8)}…)`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const uploadCsv = async (file: File) => {
    if (!selection.deploymentId) {
      toast.warning("Pick a deployment first");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch<CsvSummary>(
        `/ml/test/upload-csv?deployment_id=${encodeURIComponent(selection.deploymentId)}`,
        { method: "POST", body: form },
      );
      setCsvSummary(res);
      toast.success(`Scored ${res.n_rows} rows`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Batch inference</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <DeploymentPicker
            label="Deployment"
            value={selection.deploymentId}
            onChange={(deploymentId) => setSelection({ deploymentId })}
          />
          <SymbolsInput
            label="Symbols"
            value={selection.symbols}
            onChange={(symbols) => setSelection({ symbols })}
          />
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="batch-start">Start</Label>
              <Input
                id="batch-start"
                value={selection.start}
                onChange={(e) => setSelection({ start: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="batch-end">End</Label>
              <Input
                id="batch-end"
                value={selection.end}
                onChange={(e) => setSelection({ end: e.target.value })}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="batch-last-n">Tail rows (per symbol)</Label>
              <Input
                id="batch-last-n"
                type="number"
                value={lastN}
                onChange={(e) => setLastN(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="batch-iceberg">
                Iceberg identifier <span className="opacity-60">(optional)</span>
              </Label>
              <Input
                id="batch-iceberg"
                value={icebergId}
                placeholder="aqp_gold_features.alpha158"
                onChange={(e) => setIcebergId(e.target.value)}
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={launchBatch}
              disabled={submitting || !selection.deploymentId}
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <PlayCircle className="h-4 w-4" />
              )}
              Run batch
            </Button>
            <Button
              variant="outline"
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={!selection.deploymentId}
            >
              <UploadIcon className="h-4 w-4" />
              Upload CSV
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void uploadCsv(file);
                e.target.value = "";
              }}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Output</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <StreamLog taskId={selection.lastTaskId ?? null} maxHeight={200} />

          {csvSummary ? (
            <div className="space-y-2 rounded-md border border-[var(--border-default)] p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase tracking-wide text-[var(--text-secondary)]">
                  CSV scoring
                </span>
                <Badge variant="positive">{csvSummary.n_rows} rows</Badge>
              </div>
              <div className="grid grid-cols-4 gap-2 text-xs">
                {(["mean", "std", "min", "max"] as const).map((k) => (
                  <div key={k} className="rounded bg-[var(--bg-app)] p-2">
                    <div className="text-[10px] uppercase text-[var(--text-secondary)]">{k}</div>
                    <div className="font-mono">{csvSummary.predictions_summary[k].toFixed(4)}</div>
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
