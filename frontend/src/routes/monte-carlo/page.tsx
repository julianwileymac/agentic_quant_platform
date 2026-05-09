import { Activity } from "lucide-react";
import { useState } from "react";

import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PercentileFan } from "@/components/monte-carlo/PercentileFan";
import { TerminalHistogram } from "@/components/monte-carlo/TerminalHistogram";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

interface MonteCarloResponse {
  /** [paths][steps] price matrix. */
  paths: number[][];
  /** Final-step values per path. */
  terminal: number[];
  summary: { mean: number; std: number; p5: number; p95: number };
}

export function MonteCarloRoute() {
  const [s0, setS0] = useState(100);
  const [mu, setMu] = useState(0.07);
  const [sigma, setSigma] = useState(0.2);
  const [steps, setSteps] = useState(252);
  const [paths, setPaths] = useState(500);
  const [seed, setSeed] = useState(42);
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [result, setResult] = useState<MonteCarloResponse | null>(null);

  const run = async () => {
    setBusy(true);
    setStale(false);
    try {
      const res = await apiFetch<MonteCarloResponse>("/agents/tools/monte_carlo_tool/run", {
        method: "POST",
        body: JSON.stringify({ s0, mu, sigma, steps, paths, seed }),
      });
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        toast.warning("monte_carlo_tool not registered; running local GBM");
        const local = simulateGbm({ s0, mu, sigma, steps, paths, seed });
        setResult(local);
        setStale(true);
      } else {
        toast.error(`Simulation failed: ${(err as Error).message}`);
      }
    } finally {
      setBusy(false);
    }
  };

  const metrics: Metric[] = [
    { label: "Paths", value: paths, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Steps", value: steps, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Mean (terminal)", value: result?.summary.mean ?? null, kind: "money", digits: 2, tone: "neutral" },
    { label: "Std (terminal)", value: result?.summary.std ?? null, kind: "money", digits: 2, tone: "neutral" },
    { label: "p5", value: result?.summary.p5 ?? null, kind: "money", digits: 2, tone: "auto" },
    { label: "p95", value: result?.summary.p95 ?? null, kind: "money", digits: 2, tone: "auto" },
  ];

  return (
    <PageContainer
      title="Monte Carlo"
      subtitle="Geometric-Brownian-motion path simulator. POSTs to monte_carlo_tool with a deterministic local fallback."
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Inputs</CardTitle>
            {stale ? <Badge variant="warn">local fallback</Badge> : null}
          </CardHeader>
          <CardContent className="grid gap-3">
            <NumField id="mc-s0" label="Starting price" value={s0} onChange={setS0} step={1} />
            <NumField id="mc-mu" label="Drift μ" value={mu} onChange={setMu} step={0.01} />
            <NumField id="mc-sigma" label="Volatility σ" value={sigma} onChange={setSigma} step={0.01} />
            <NumField id="mc-steps" label="Steps" value={steps} onChange={setSteps} step={1} />
            <NumField id="mc-paths" label="Paths" value={paths} onChange={setPaths} step={1} />
            <NumField id="mc-seed" label="Seed" value={seed} onChange={setSeed} step={1} />
            <Button onClick={run} disabled={busy} className="gap-2">
              <Activity className="h-4 w-4" /> {busy ? "Running…" : "Run simulation"}
            </Button>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-3">
          <MetricsGrid metrics={metrics} columns={6} />
          <Card className="h-[300px]">
            <CardHeader>
              <CardTitle>Percentile fan</CardTitle>
            </CardHeader>
            <CardContent className="h-full p-3">
              <PercentileFan paths={result?.paths ?? []} />
            </CardContent>
          </Card>
          <Card className="h-[260px]">
            <CardHeader>
              <CardTitle>Terminal value histogram</CardTitle>
            </CardHeader>
            <CardContent className="h-full p-3">
              <TerminalHistogram values={result?.terminal ?? []} />
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}

function NumField({
  id,
  label,
  value,
  onChange,
  step,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (v: number) => void;
  step: number;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        className="font-mono"
        step={step}
        value={value}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onChange(n);
        }}
      />
    </div>
  );
}

/**
 * Hermetic GBM path simulator using a Mulberry32 PRNG (deterministic
 * given a seed). Used as a 404 fallback when the backend tool isn't
 * registered. Step-frequency assumed 1 / year.
 */
function simulateGbm({
  s0,
  mu,
  sigma,
  steps,
  paths,
  seed,
}: {
  s0: number;
  mu: number;
  sigma: number;
  steps: number;
  paths: number;
  seed: number;
}): MonteCarloResponse {
  const dt = 1 / steps;
  const rng = mulberry32(seed);
  const matrix: number[][] = [];
  const terminal: number[] = [];
  for (let p = 0; p < paths; p += 1) {
    const series = [s0];
    let s = s0;
    for (let t = 1; t < steps; t += 1) {
      const z = boxMuller(rng);
      s *= Math.exp((mu - 0.5 * sigma * sigma) * dt + sigma * Math.sqrt(dt) * z);
      series.push(s);
    }
    matrix.push(series);
    const last = series[series.length - 1];
    if (typeof last === "number") terminal.push(last);
  }
  const sum = terminal.reduce((a, b) => a + b, 0);
  const mean = sum / Math.max(1, terminal.length);
  const variance =
    terminal.reduce((a, b) => a + (b - mean) * (b - mean), 0) /
    Math.max(1, terminal.length - 1);
  const std = Math.sqrt(variance);
  const sorted = [...terminal].sort((a, b) => a - b);
  const p5 = sorted[Math.floor(sorted.length * 0.05)] ?? 0;
  const p95 = sorted[Math.floor(sorted.length * 0.95)] ?? 0;
  return { paths: matrix, terminal, summary: { mean, std, p5, p95 } };
}

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function boxMuller(rng: () => number): number {
  const u1 = Math.max(rng(), 1e-12);
  const u2 = rng();
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}
