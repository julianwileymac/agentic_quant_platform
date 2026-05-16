import { Loader2, Radar } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CodeEditor } from "@/components/common/CodeEditor";
import { DeploymentPicker } from "@/components/strategy-dev/DeploymentPicker";
import { useStrategyDev } from "@/components/strategy-dev/StrategyDevLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

interface ScenarioResp {
  baseline_prediction: number;
  rows: { feature: string; perturbation: number; prediction: number; delta: number }[];
}

/**
 * Sensitivity / what-if sweep. Calls `POST /ml/test/scenario` sync by
 * default. Visualises deltas as bar + table.
 */
export function ScenarioPerturbationRoute() {
  const { selection, setSelection } = useStrategyDev();
  const [busy, setBusy] = useState(false);
  const [baseline, setBaseline] = useState<number | null>(null);
  const [rows, setRows] = useState<ScenarioResp["rows"]>([]);
  const [perturbationsText, setPerturbationsText] = useState(
    selection.perturbations.join(","),
  );

  const launch = async () => {
    if (!selection.deploymentId) {
      toast.warning("Pick a deployment first");
      return;
    }
    let featureRow: Record<string, number>;
    try {
      const parsed = JSON.parse(selection.featureRowText || "{}") as Record<string, unknown>;
      featureRow = {};
      for (const [k, v] of Object.entries(parsed)) {
        const n = typeof v === "number" ? v : Number(v);
        if (Number.isFinite(n)) featureRow[k] = n;
      }
    } catch (err) {
      toast.error(`Invalid JSON: ${(err as Error).message}`);
      return;
    }
    const perturbations = perturbationsText
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => Number.isFinite(n));
    if (!perturbations.length) {
      toast.warning("Provide at least one perturbation (comma-separated decimals)");
      return;
    }
    setSelection({ perturbations });
    setBusy(true);
    setRows([]);
    setBaseline(null);
    try {
      const res = await apiFetch<ScenarioResp>("/ml/test/scenario", {
        method: "POST",
        body: JSON.stringify({
          deployment_id: selection.deploymentId,
          feature_row: featureRow,
          perturbations,
          sync: true,
        }),
      });
      setBaseline(res.baseline_prediction);
      setRows(res.rows ?? []);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const chartData = useMemo(
    () =>
      rows.map((r, i) => ({
        idx: i,
        label: `${r.feature} ${(r.perturbation * 100).toFixed(0)}%`,
        delta: r.delta,
      })),
    [rows],
  );

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Sensitivity sweep</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <DeploymentPicker
            label="Deployment"
            value={selection.deploymentId}
            onChange={(deploymentId) => setSelection({ deploymentId })}
          />
          <div className="space-y-1">
            <Label>Baseline feature row (JSON)</Label>
            <div className="h-32 overflow-hidden rounded-md">
              <CodeEditor
                language="json"
                value={selection.featureRowText}
                onChange={(featureRowText) => setSelection({ featureRowText })}
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="scenario-perts">Perturbations (decimals, comma-separated)</Label>
            <Input
              id="scenario-perts"
              value={perturbationsText}
              onChange={(e) => setPerturbationsText(e.target.value)}
              placeholder="-0.2,-0.1,0,0.1,0.2"
            />
          </div>
          <Button onClick={launch} disabled={busy || !selection.deploymentId}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
            Sweep
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sensitivity table</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="text-xs text-[var(--text-secondary)]">Run a sweep to see results.</p>
          ) : (
            <div className="space-y-3">
              {baseline !== null ? (
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-[var(--text-secondary)]">Baseline:</span>
                  <Badge variant="secondary" className="font-mono">{baseline.toFixed(6)}</Badge>
                </div>
              ) : null}
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="idx" hide />
                    <YAxis fontSize={11} width={48} />
                    <Tooltip
                      formatter={(value, _name, item) => [
                        Number(value).toFixed(4),
                        (item?.payload as { label?: string } | undefined)?.label ?? "delta",
                      ]}
                    />
                    <Bar dataKey="delta">
                      {chartData.map((row) => (
                        <Cell key={row.idx} fill={row.delta >= 0 ? "#10b981" : "#ef4444"} />
                      ))}
                    </Bar>
                    <Legend />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="max-h-72 overflow-auto rounded-md border border-[var(--border-default)]">
                <table className="w-full text-xs">
                  <thead className="bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
                    <tr>
                      <th className="px-2 py-1 text-left">Feature</th>
                      <th className="px-2 py-1 text-right">Perturbation</th>
                      <th className="px-2 py-1 text-right">Prediction</th>
                      <th className="px-2 py-1 text-right">Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={`${r.feature}:${r.perturbation}`} className="border-t border-[var(--border-subtle)]">
                        <td className="px-2 py-1 font-mono">{r.feature}</td>
                        <td className="px-2 py-1 text-right">{(r.perturbation * 100).toFixed(1)}%</td>
                        <td className="px-2 py-1 text-right font-mono">{r.prediction.toFixed(4)}</td>
                        <td
                          className={`px-2 py-1 text-right font-mono ${
                            r.delta >= 0 ? "text-[var(--pos-fg)]" : "text-[var(--neg-fg)]"
                          }`}
                        >
                          {r.delta.toFixed(4)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
