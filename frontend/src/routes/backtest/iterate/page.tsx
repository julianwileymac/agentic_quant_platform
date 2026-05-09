import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, PlayCircle, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { BacktestApi } from "@/lib/api/backtest";

const REGIME_OPTIONS = [
  { id: "", label: "Auto-detect (no warm start)" },
  { id: "crisis", label: "Crisis (VIX >= 95th percentile)" },
  { id: "high_vol", label: "High volatility" },
  { id: "mid_vol", label: "Mid volatility" },
  { id: "low_vol", label: "Low volatility" },
];

/**
 * Phase-4 agent-driven iterative optimisation surface.
 *
 * Submits a strategy + base config + target Sharpe + regime hint to
 * ``POST /backtest/iterate``. The Celery task warm-starts from
 * regime memory, runs a backtest, asks the parameter_mutator agent
 * to propose new params, and repeats until the target is met or
 * the iteration cap is reached.
 *
 * The page deliberately lives alongside the manual /backtest/new
 * builder rather than replacing it — different mental model
 * (single run vs. closed-loop research cycle).
 */
export function BacktestIterateRoute() {
  const [strategyId, setStrategyId] = useState("BBadXMacDrSi");
  const [targetSharpe, setTargetSharpe] = useState("1.5");
  const [maxIterations, setMaxIterations] = useState("8");
  const [regime, setRegime] = useState("");
  const [baseConfig, setBaseConfig] = useState(
    JSON.stringify(
      {
        strategy: { class: "BBadXMacDrSi", module_path: "aqp.strategies.bbadx_macdrsi" },
        data_source: { kind: "bars_default" },
        symbols: ["AAPL.NASDAQ", "MSFT.NASDAQ"],
        start: "2022-01-01",
        end: "2024-12-31",
        initial_cash: 100_000,
        params: { lookback: 20, threshold: 25 },
      },
      null,
      2,
    ),
  );
  const [history, setHistory] = useState<Array<{ task_id: string; submitted_at: string; sharpe_target: number }>>([]);

  const iterate = useMutation({
    mutationFn: async () => {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(baseConfig);
      } catch (err) {
        throw new Error(`base_config is not valid JSON: ${(err as Error).message}`);
      }
      const body: {
        strategy_id: string;
        base_config: Record<string, unknown>;
        target_sharpe: number;
        max_iterations: number;
        regime?: string;
      } = {
        strategy_id: strategyId,
        base_config: parsed,
        target_sharpe: Number(targetSharpe),
        max_iterations: Number(maxIterations),
      };
      if (regime) {
        body.regime = regime;
      }
      return BacktestApi.iterate(body);
    },
    onSuccess: (data) => {
      setHistory((prev) =>
        [
          {
            task_id: data.task_id,
            submitted_at: new Date().toISOString(),
            sharpe_target: Number(targetSharpe),
          },
          ...prev,
        ].slice(0, 8),
      );
      toast.success("Iterative optimisation queued", {
        description: `Task ${data.task_id}`,
      });
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error("Submission failed", { description: message });
    },
  });

  return (
    <PageContainer
      title="Iterative optimisation"
      subtitle="Closed-loop research cycle: warm-start from regime memory, mutate via the parameter_mutator agent, stop on target Sharpe."
      extra={
        <Button asChild variant="outline" size="sm">
          <Link to="/backtest">
            <ArrowLeft className="h-4 w-4" /> Back
          </Link>
        </Button>
      }
    >
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Sparkles className="h-4 w-4" /> Iteration parameters
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="strategy_id">Strategy registry name</Label>
              <Input
                id="strategy_id"
                value={strategyId}
                onChange={(e) => setStrategyId(e.target.value)}
                placeholder="e.g. BBadXMacDrSi"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="target_sharpe">Target Sharpe</Label>
              <Input
                id="target_sharpe"
                value={targetSharpe}
                onChange={(e) => setTargetSharpe(e.target.value)}
                inputMode="decimal"
                placeholder="1.5"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="max_iterations">Max iterations</Label>
              <Input
                id="max_iterations"
                value={maxIterations}
                onChange={(e) => setMaxIterations(e.target.value)}
                inputMode="numeric"
                placeholder="8"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="regime">Regime hint</Label>
              <select
                id="regime"
                value={regime}
                onChange={(e) => setRegime(e.target.value)}
                className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 text-sm"
              >
                {REGIME_OPTIONS.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <Label htmlFor="base_config">Base backtest config (JSON)</Label>
            <textarea
              id="base_config"
              value={baseConfig}
              onChange={(e) => setBaseConfig(e.target.value)}
              rows={14}
              className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 font-mono text-xs"
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button onClick={() => iterate.mutate()} disabled={iterate.isPending}>
              <PlayCircle className="h-4 w-4" />
              {iterate.isPending ? "Submitting…" : "Start iteration loop"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {history.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Recent submissions</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            {history.map((row) => (
              <div
                key={row.task_id}
                className="flex items-center justify-between rounded border border-[var(--border-default)] p-2"
              >
                <span className="font-mono">{row.task_id}</span>
                <Badge variant="secondary">target sharpe {row.sharpe_target}</Badge>
                <span className="text-xs text-[var(--text-muted)]">{row.submitted_at}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </PageContainer>
  );
}
