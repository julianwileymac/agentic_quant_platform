import { Loader2, Play } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

import { useStrategyDev } from "./StrategyDevLayout";
import { StreamLog } from "./StreamLog";
import { SymbolsInput } from "./SymbolsInput";

type SimulationKind =
  | "backtest"
  | "paper"
  | "lob"
  | "alpha_backtest"
  | "rl";

interface TaskAcceptedResponse {
  task_id: string;
  status?: string;
  stream_url?: string;
}

const KIND_LABELS: { key: SimulationKind; label: string; subtitle: string }[] = [
  { key: "backtest", label: "Backtest", subtitle: "Event-driven / vectorised backtest" },
  { key: "paper", label: "Paper", subtitle: "Forward-test via paper broker" },
  { key: "lob", label: "LOB / HFT", subtitle: "Tick-replay through hftbacktest" },
  { key: "alpha_backtest", label: "Alpha-Backtest", subtitle: "Train + backtest combined" },
  { key: "rl", label: "RL", subtitle: "RLRuntime training run" },
];

/**
 * Unified simulation launcher. Targets the right runtime based on
 * which simulation kind is selected; all paths emit `TaskAccepted`
 * (`task_id`, `stream_url`) so the persistent KPI strip + StreamLog
 * always work the same way.
 */
export function SimulationCreator() {
  const { selection, setSelection } = useStrategyDev();
  const [kind, setKind] = useState<SimulationKind>("backtest");
  const [submitting, setSubmitting] = useState(false);

  // LOB-specific knobs.
  const [lobStrategy, setLobStrategy] = useState("AvellanedaStoikovMM");
  const [lobPreset, setLobPreset] = useState("lob_btcusdt_sample");
  const [lobMaxEvents, setLobMaxEvents] = useState(1_000_000);

  // RL-specific knobs.
  const [rlSpec, setRlSpec] = useState("");

  const launch = async () => {
    setSubmitting(true);
    try {
      let res: TaskAcceptedResponse;
      switch (kind) {
        case "backtest": {
          if (!selection.strategyId) {
            toast.warning("Save a strategy in the composer first or pick one from the library");
            return;
          }
          res = await apiFetch<TaskAcceptedResponse>(
            `/strategies/${encodeURIComponent(selection.strategyId)}/backtest`,
            {
              method: "POST",
              body: JSON.stringify({
                symbols: selection.symbols,
                start: selection.start,
                end: selection.end,
              }),
            },
          );
          break;
        }
        case "paper": {
          if (!selection.strategyId) {
            toast.warning("Save a strategy in the composer first or pick one from the library");
            return;
          }
          res = await apiFetch<TaskAcceptedResponse>("/paper/sessions", {
            method: "POST",
            body: JSON.stringify({
              strategy_id: selection.strategyId,
              symbols: selection.symbols,
            }),
          });
          break;
        }
        case "lob": {
          res = await apiFetch<TaskAcceptedResponse>("/backtest/lob", {
            method: "POST",
            body: JSON.stringify({
              strategy: lobStrategy,
              dataset_preset: lobPreset,
              latency_profile: "intp_order_latency",
              queue_model: "probabilistic",
              max_events: lobMaxEvents,
              snapshot_every: 5_000,
            }),
          });
          break;
        }
        case "alpha_backtest": {
          if (!selection.strategyId) {
            toast.warning("Save a strategy in the composer first");
            return;
          }
          res = await apiFetch<TaskAcceptedResponse>("/ml/alpha-backtest-runs", {
            method: "POST",
            body: JSON.stringify({
              strategy_id: selection.strategyId,
              backtest_cfg: {
                symbols: selection.symbols,
                start: selection.start,
                end: selection.end,
              },
              train_first: false,
              deployment_id: selection.deploymentId || undefined,
            }),
          });
          break;
        }
        case "rl": {
          if (!rlSpec.trim()) {
            toast.warning("Provide an RLExperimentSpec id");
            return;
          }
          res = await apiFetch<TaskAcceptedResponse>(
            `/rl/experiments/${encodeURIComponent(rlSpec.trim())}/train`,
            { method: "POST", body: JSON.stringify({}) },
          );
          break;
        }
      }
      setSelection({
        lastTaskId: res!.task_id,
        lastRunSummary: { runId: res!.task_id, kind: kind === "alpha_backtest" ? "alpha_backtest" : kind },
      });
      toast.success(`${kind} queued (${res!.task_id.slice(0, 8)}…)`);
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
          <CardTitle>Simulation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Tabs value={kind} onValueChange={(v) => setKind(v as SimulationKind)}>
            <TabsList className="flex w-full flex-wrap gap-1">
              {KIND_LABELS.map((k) => (
                <TabsTrigger key={k.key} value={k.key} className="text-[11px]">
                  {k.label}
                </TabsTrigger>
              ))}
            </TabsList>
            {KIND_LABELS.map((k) => (
              <TabsContent key={k.key} value={k.key} className="space-y-3 pt-3">
                <p className="text-xs text-[var(--text-secondary)]">{k.subtitle}</p>
                {(k.key === "backtest" || k.key === "paper" || k.key === "alpha_backtest") && (
                  <>
                    <SymbolsInput
                      label="Symbols"
                      value={selection.symbols}
                      onChange={(symbols) => setSelection({ symbols })}
                    />
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <Label htmlFor={`${k.key}-start`}>Start</Label>
                        <Input
                          id={`${k.key}-start`}
                          value={selection.start}
                          onChange={(e) => setSelection({ start: e.target.value })}
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor={`${k.key}-end`}>End</Label>
                        <Input
                          id={`${k.key}-end`}
                          value={selection.end}
                          onChange={(e) => setSelection({ end: e.target.value })}
                        />
                      </div>
                    </div>
                    <Badge variant="outline" className="text-[10px]">
                      strategy {selection.strategyId ?? "—"}
                    </Badge>
                  </>
                )}
                {k.key === "lob" && (
                  <>
                    <div className="space-y-1">
                      <Label htmlFor="sim-lob-strat">Strategy</Label>
                      <Input
                        id="sim-lob-strat"
                        value={lobStrategy}
                        onChange={(e) => setLobStrategy(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="sim-lob-preset">Dataset preset</Label>
                      <Input
                        id="sim-lob-preset"
                        value={lobPreset}
                        onChange={(e) => setLobPreset(e.target.value)}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="sim-lob-events">Max events</Label>
                      <Input
                        id="sim-lob-events"
                        type="number"
                        value={lobMaxEvents}
                        onChange={(e) => setLobMaxEvents(Number(e.target.value))}
                      />
                    </div>
                  </>
                )}
                {k.key === "rl" && (
                  <div className="space-y-1">
                    <Label htmlFor="sim-rl-spec">RLExperimentSpec id</Label>
                    <Input
                      id="sim-rl-spec"
                      value={rlSpec}
                      onChange={(e) => setRlSpec(e.target.value)}
                      placeholder="rl-exp-uuid-or-name"
                    />
                  </div>
                )}
              </TabsContent>
            ))}
          </Tabs>
          <Button onClick={launch} disabled={submitting}>
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Launch
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Stream</CardTitle>
        </CardHeader>
        <CardContent>
          <StreamLog taskId={selection.lastTaskId ?? null} maxHeight={400} />
        </CardContent>
      </Card>
    </div>
  );
}
