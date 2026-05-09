import { Loader2, Play } from "lucide-react";
import { useState } from "react";

import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { AgentsApi, type AgentRunDetail } from "@/lib/api/agents";

interface Props {
  specName: string;
  title: string;
  description?: string;
  defaultPrompt?: string;
}

/**
 * Generic per-spec agent console. Drives every leaf route under
 * `/agents/{selection,trader,research/*,analysis/*}` from a single
 * `AgentSpec` name. Posts to `POST /agents/runs/v2/sync` and renders
 * the populated `AgentRunDetail` as a metrics grid + raw output JSON.
 */
export function AgentTeamConsole({ specName, title, description, defaultPrompt }: Props) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AgentRunDetail | null>(null);
  const [vtSymbol, setVtSymbol] = useState("");
  const [asOf, setAsOf] = useState("");
  const [universe, setUniverse] = useState("");
  const [modelId, setModelId] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [prompt, setPrompt] = useState(defaultPrompt ?? "");

  const onRun = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const inputs: Record<string, unknown> = {};
      if (vtSymbol.trim()) inputs.vt_symbol = vtSymbol.trim();
      if (asOf.trim()) inputs.as_of = asOf.trim();
      if (universe.trim())
        inputs.universe = universe.split(",").map((s) => s.trim()).filter(Boolean);
      if (prompt.trim()) inputs.prompt = prompt.trim();
      if (modelId.trim()) inputs.model_id = modelId.trim();
      if (strategyId.trim()) inputs.strategy_id = strategyId.trim();

      const res = await AgentsApi.runSpecSync(specName, inputs);
      setResult(res);
      toast.success(`run ${(res.id ?? "").slice(0, 12)} ${res.status ?? "ok"}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`run failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  };

  const metrics: Metric[] = [
    { label: "Cost", value: result?.cost_usd ?? null, kind: "money", digits: 4, tone: "neutral" },
    { label: "Calls", value: result?.n_calls ?? null, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Tool calls", value: result?.n_tool_calls ?? null, kind: "integer", digits: 0, tone: "neutral" },
    { label: "RAG hits", value: result?.n_rag_hits ?? null, kind: "integer", digits: 0, tone: "neutral" },
    {
      label: "Guardrails",
      value: result?.guardrail_failures ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
    },
    {
      label: "Tokens (in/out)",
      value: null,
      kind: "decimal",
      hint: (
        <span className="font-mono">
          {(result?.tokens_in ?? "—") + " / " + (result?.tokens_out ?? "—")}
        </span>
      ),
    },
  ];

  return (
    <PageContainer
      title={title}
      subtitle={
        <span>
          {description ?? "Spec-driven agent console."} <code className="font-mono">{specName}</code>
        </span>
      }
      extra={result?.status ? <Badge variant="secondary">{result.status}</Badge> : null}
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[420px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Run</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={onRun} className="grid gap-3">
              <Field id="vt_symbol" label="vt_symbol" value={vtSymbol} onChange={setVtSymbol} placeholder="AAPL.NASDAQ" />
              <Field id="as_of" label="as_of" value={asOf} onChange={setAsOf} placeholder="2026-04-27 (optional)" />
              <Field id="universe" label="universe (comma-separated)" value={universe} onChange={setUniverse} placeholder="AAPL.NASDAQ, MSFT.NASDAQ" />
              <Field id="model_id" label="model_id" value={modelId} onChange={setModelId} placeholder="alpha158_lgbm (optional)" />
              <Field id="strategy_id" label="strategy_id" value={strategyId} onChange={setStrategyId} placeholder="momentum (optional)" />
              <div className="flex flex-col gap-1">
                <Label htmlFor="prompt">prompt</Label>
                <textarea
                  id="prompt"
                  className="min-h-[100px] rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[var(--info-fg)]"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Free-form instruction for the agent"
                />
              </div>
              <Button type="submit" disabled={busy} className="gap-2">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {busy ? "Running…" : "Run synchronously"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-3">
          <MetricsGrid metrics={metrics} columns={6} />
          <Card className="flex-1">
            <CardHeader>
              <CardTitle>Output</CardTitle>
              {result ? (
                <span className="font-mono text-[10px] text-[var(--text-secondary)]">
                  {result.id?.slice(0, 12)}
                </span>
              ) : null}
            </CardHeader>
            <CardContent>
              {!result ? (
                <p className="text-sm italic text-[var(--text-secondary)]">
                  Submit the form to run a sync agent invocation. Output and step traces appear here.
                </p>
              ) : (
                <pre className="max-h-[420px] overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs">
                  {JSON.stringify(result.output ?? {}, null, 2)}
                </pre>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        {...(placeholder ? { placeholder } : {})}
        className="font-mono"
      />
    </div>
  );
}
