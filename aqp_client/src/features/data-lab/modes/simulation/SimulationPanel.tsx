import { Pause, Play, Rewind } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { useLabStore } from "@/features/data-lab/state/labStore";
import { useLabChannel } from "@/features/data-lab/ws/useLabChannel";

type SimEnv = "hftbt" | "stochastic" | "rl" | "optctl";

interface SimConfig {
  env: SimEnv;
  seed: number;
  speed: number;
  capital: number;
  fee_bps: number;
  latency_ns: number;
}

const DEFAULT_CONFIG: SimConfig = {
  env: "hftbt",
  seed: 42,
  speed: 1.0,
  capital: 1_000_000,
  fee_bps: 1.0,
  latency_ns: 250_000,
};

const ENV_LABEL: Record<SimEnv, string> = {
  hftbt: "hftbacktest LOB",
  stochastic: "Monte Carlo (JAX vmap)",
  rl: "RL env + SB3 trainer",
  optctl: "Optimal control (A-S / C-J / O-W)",
};

/**
 * Simulation mode panel — Phase 4 implementation.
 *
 * Surfaces the env config banner + transport bar + live tick log.
 * The compute backend lives in :mod:`aqp.lab.simulation` and runs
 * inside :class:`SandboxRuntime` per the simulation compiler. WS
 * envelopes (sim.tick / stream.market / stream.pnl) flow through
 * the standard ``useLabChannel`` plumbing.
 *
 * Frontend rule 3: when an env is running we apply the amber
 * ``[SANDBOX]`` outline at the LabShell level — this component just
 * wires the controls.
 */
export function SimulationPanel() {
  const sessionId = useLabStore((s) => s.sessionId);
  const recentEnvelopes = useLabStore((s) => s.recentEnvelopes);
  const [cfg, setCfg] = useState<SimConfig>(DEFAULT_CONFIG);
  const [paused, setPaused] = useState(false);
  const channel = useLabChannel({ sessionId });

  const sendCommand = useCallback(
    (cmd: "pause" | "resume" | "step" | "seed" | "speed", value?: unknown) => {
      channel.send({
        kind: "sim.command",
        run_id: "current",
        cmd,
        value,
        v: 1,
      });
      if (cmd === "pause") setPaused(true);
      if (cmd === "resume") setPaused(false);
      toast.info(`sim.command sent: ${cmd}`);
    },
    [channel],
  );

  const liveTicks = recentEnvelopes.filter(
    (e) => e.kind === "sim.tick" || e.kind === "stream.market",
  );

  const pnlSeries = useMemo(
    () =>
      recentEnvelopes
        .filter((e) => e.kind === "sim.tick")
        .map((e) => ({
          t: new Date(e.timestamp * 1000).toISOString().slice(11, 23),
          pnl: typeof e.pnl === "number" ? e.pnl : null,
          pos: typeof e.pos === "number" ? e.pos : null,
        }))
        .filter((row) => row.pnl !== null)
        .slice(-200),
    [recentEnvelopes],
  );

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_1fr] gap-2">
      <Card>
        <CardContent className="grid grid-cols-2 gap-3 py-3 md:grid-cols-6">
          <div className="space-y-1">
            <Label>Env</Label>
            <select
              className="w-full rounded-md border bg-background p-2 text-sm"
              value={cfg.env}
              onChange={(e) => setCfg({ ...cfg, env: e.target.value as SimEnv })}
            >
              {Object.entries(ENV_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label>Seed</Label>
            <Input
              type="number"
              value={cfg.seed}
              onChange={(e) => setCfg({ ...cfg, seed: Number(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label>Speed</Label>
            <Input
              type="number"
              step="0.1"
              value={cfg.speed}
              onChange={(e) => setCfg({ ...cfg, speed: Number(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label>Capital</Label>
            <Input
              type="number"
              value={cfg.capital}
              onChange={(e) => setCfg({ ...cfg, capital: Number(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label>Fee (bps)</Label>
            <Input
              type="number"
              step="0.1"
              value={cfg.fee_bps}
              onChange={(e) => setCfg({ ...cfg, fee_bps: Number(e.target.value) })}
            />
          </div>
          <div className="space-y-1">
            <Label>Latency (ns)</Label>
            <Input
              type="number"
              value={cfg.latency_ns}
              onChange={(e) => setCfg({ ...cfg, latency_ns: Number(e.target.value) })}
            />
          </div>
          <div className="col-span-2 flex items-center gap-2 md:col-span-6">
            <Badge variant="warn">[SANDBOX]</Badge>
            <span className="text-xs text-muted-foreground">
              Frontend rule 3 — simulation runs apply the amber outline
              + tab-title prefix. Live order routing remains out of scope
              for the Lab page.
            </span>
            <div className="flex-1" />
            <div className="flex items-center gap-2">
              <Label htmlFor="sim-speed-slider" className="text-[11px]">
                Speed {cfg.speed.toFixed(1)}×
              </Label>
              <input
                id="sim-speed-slider"
                type="range"
                min={0}
                max={4}
                step={0.1}
                value={Math.log10(Math.max(1, cfg.speed))}
                onChange={(e) => {
                  const next = Math.pow(10, Number(e.target.value));
                  setCfg({ ...cfg, speed: next });
                  sendCommand("speed", next);
                }}
                className="w-40 accent-sky-500"
                title="Tick-rate throttle (1× to 10000×)"
              />
            </div>
            <Button variant="outline" size="sm" onClick={() => sendCommand("step")} className="gap-2">
              <Rewind className="h-4 w-4" /> Step
            </Button>
            {paused ? (
              <Button size="sm" onClick={() => sendCommand("resume")} className="gap-2">
                <Play className="h-4 w-4" /> Resume
              </Button>
            ) : (
              <Button size="sm" onClick={() => sendCommand("pause")} className="gap-2">
                <Pause className="h-4 w-4" /> Pause
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
      <div className="grid min-h-0 gap-2 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <CardContent className="space-y-1 py-2">
            <div className="text-sm font-medium">Tick stream</div>
            <div className="h-64 overflow-auto rounded bg-muted/30 p-2 font-mono text-[11px]">
              {liveTicks.length === 0 ? (
                <span className="text-muted-foreground">
                  Waiting for sim.tick / stream.market envelopes…
                </span>
              ) : (
                liveTicks.slice(-50).map((env, i) => (
                  <div key={i}>
                    {new Date(env.timestamp * 1000).toISOString().slice(11, 23)}{" "}
                    <span className="text-sky-400">{env.kind}</span>{" "}
                    {env.kind === "sim.tick" ? (
                      <>
                        pnl={env.pnl?.toFixed(2) ?? "—"} pos={env.pos ?? "—"}
                      </>
                    ) : (
                      <>topic={env.topic}</>
                    )}
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
        <Card className="overflow-hidden">
          <CardContent className="space-y-1 py-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              PnL + position
              <Badge variant="outline" className="ml-auto">
                {pnlSeries.length} ticks
              </Badge>
            </div>
            <div className="h-64">
              {pnlSeries.length === 0 ? (
                <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                  Waiting for sim.tick envelopes with pnl / pos…
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={pnlSeries}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis
                      dataKey="t"
                      tick={{ fontSize: 10 }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      yAxisId="pnl"
                      tick={{ fontSize: 10 }}
                      tickFormatter={(v) =>
                        typeof v === "number" ? v.toLocaleString() : String(v)
                      }
                    />
                    <YAxis
                      yAxisId="pos"
                      orientation="right"
                      tick={{ fontSize: 10 }}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border-default)",
                        fontSize: 11,
                      }}
                    />
                    <Line
                      yAxisId="pnl"
                      type="monotone"
                      dataKey="pnl"
                      dot={false}
                      stroke="#10b981"
                      strokeWidth={1.5}
                      name="PnL"
                    />
                    <Line
                      yAxisId="pos"
                      type="monotone"
                      dataKey="pos"
                      dot={false}
                      stroke="#0ea5e9"
                      strokeWidth={1}
                      name="Position"
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default SimulationPanel;
