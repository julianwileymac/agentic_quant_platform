import { Calculator } from "lucide-react";
import { useState } from "react";

import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PayoffChart } from "@/components/options/PayoffChart";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

type Model = "bachelier" | "inverse";

interface GreeksResponse {
  price: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  vanna?: number;
  volga?: number;
  veta?: number;
  [key: string]: unknown;
}

export function OptionsLabRoute() {
  const [forward, setForward] = useState(100);
  const [strike, setStrike] = useState(100);
  const [tte, setTte] = useState(0.25);
  const [sigma, setSigma] = useState(0.25);
  const [isCall, setIsCall] = useState(true);
  const [model, setModel] = useState<Model>("bachelier");

  const [busy, setBusy] = useState(false);
  const [greeks, setGreeks] = useState<GreeksResponse | null>(null);
  const [stale, setStale] = useState(false);

  const compute = async () => {
    setBusy(true);
    setStale(false);
    try {
      const res = await apiFetch<GreeksResponse>("/agents/tools/option_greeks_tool/run", {
        method: "POST",
        body: JSON.stringify({
          forward,
          strike,
          time_to_expiry_years: tte,
          sigma,
          is_call: isCall,
          model,
        }),
      });
      setGreeks(res);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        toast.warning("option_greeks_tool not registered; using local Bachelier fallback");
        setGreeks(localBachelier({ forward, strike, tte, sigma, isCall }));
        setStale(true);
      } else {
        toast.error(`Greeks failed: ${(err as Error).message}`);
      }
    } finally {
      setBusy(false);
    }
  };

  const metrics: Metric[] = [
    { label: "Price", value: greeks?.price ?? null, kind: "money", digits: 4, tone: "neutral" },
    { label: "Delta", value: greeks?.delta ?? null, kind: "decimal", digits: 4, tone: "auto", signed: true },
    { label: "Gamma", value: greeks?.gamma ?? null, kind: "decimal", digits: 4, tone: "auto", signed: true },
    { label: "Theta", value: greeks?.theta ?? null, kind: "decimal", digits: 4, tone: "auto", signed: true },
    { label: "Vega", value: greeks?.vega ?? null, kind: "decimal", digits: 4, tone: "auto", signed: true },
    { label: "Vanna", value: (greeks?.vanna as number | undefined) ?? null, kind: "decimal", digits: 4, tone: "auto", signed: true },
    { label: "Volga", value: (greeks?.volga as number | undefined) ?? null, kind: "decimal", digits: 4, tone: "auto", signed: true },
    { label: "Veta", value: (greeks?.veta as number | undefined) ?? null, kind: "decimal", digits: 4, tone: "auto", signed: true },
  ];

  return (
    <PageContainer
      title="Options Lab"
      subtitle="Bachelier / inverse-priced vanilla Greeks. POSTs to option_greeks_tool with a local fallback."
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Inputs</CardTitle>
            {stale ? <Badge variant="warn">local fallback</Badge> : null}
          </CardHeader>
          <CardContent className="grid gap-3">
            <NumField id="opt-fwd" label="Forward price" value={forward} onChange={setForward} step={1} />
            <NumField id="opt-k" label="Strike" value={strike} onChange={setStrike} step={1} />
            <NumField id="opt-tte" label="T (years)" value={tte} onChange={setTte} step={0.01} />
            <NumField id="opt-sigma" label="Volatility" value={sigma} onChange={setSigma} step={0.01} />
            <div className="flex flex-col gap-1">
              <Label>Direction</Label>
              <div className="grid grid-cols-2 gap-1">
                <Button variant={isCall ? "positive" : "outline"} onClick={() => setIsCall(true)}>
                  Call
                </Button>
                <Button variant={!isCall ? "destructive" : "outline"} onClick={() => setIsCall(false)}>
                  Put
                </Button>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <Label>Model</Label>
              <div className="grid grid-cols-2 gap-1">
                {(["bachelier", "inverse"] as const).map((m) => (
                  <Button key={m} variant={model === m ? "default" : "outline"} onClick={() => setModel(m)} className="capitalize">
                    {m}
                  </Button>
                ))}
              </div>
            </div>
            <Button onClick={compute} disabled={busy} className="gap-2">
              <Calculator className="h-4 w-4" /> {busy ? "Computing…" : "Compute Greeks"}
            </Button>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-3">
          <MetricsGrid metrics={metrics} columns={4} />
          <Card className="h-[420px]">
            <CardHeader>
              <CardTitle>Payoff at expiry</CardTitle>
            </CardHeader>
            <CardContent className="h-full p-3">
              <PayoffChart
                forward={forward}
                strike={strike}
                isCall={isCall}
                premium={greeks?.price ?? 0}
              />
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
 * Closed-form Bachelier (normal) European-option pricer + Greeks. Used
 * as a hermetic fallback when option_greeks_tool isn't registered. Not
 * a replacement for the production wrapper — purely for the lab UI.
 */
function localBachelier({
  forward,
  strike,
  tte,
  sigma,
  isCall,
}: {
  forward: number;
  strike: number;
  tte: number;
  sigma: number;
  isCall: boolean;
}): GreeksResponse {
  const sd = sigma * Math.sqrt(tte);
  const d = (forward - strike) / Math.max(sd, 1e-12);
  const n = (z: number) => Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI);
  const N = (z: number) => 0.5 * (1 + erf(z / Math.SQRT2));
  const sign = isCall ? 1 : -1;
  const price = sign * (forward - strike) * N(sign * d) + sd * n(d);
  const delta = sign * N(sign * d);
  const gamma = n(d) / Math.max(sd, 1e-12);
  const vega = Math.sqrt(tte) * n(d);
  const theta = (-sigma * n(d)) / (2 * Math.sqrt(Math.max(tte, 1e-12)));
  return { price, delta, gamma, theta, vega };
}

function erf(x: number): number {
  // Abramowitz-Stegun 7.1.26
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y =
    1 -
    (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) *
      t *
      Math.exp(-x * x);
  return x >= 0 ? y : -y;
}
