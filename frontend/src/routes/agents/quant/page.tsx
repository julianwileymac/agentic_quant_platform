import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import {
  QuantAgentsApi,
  type AlphaProposeResponse,
  type FactorCompilePreviewResponse,
  type AlphaEvaluateResponse,
  type StrategyDispatchResponse,
} from "@/lib/api/quantAgents";

const DEFAULT_FORMULA = "Sign(EMA($close, 12) - EMA($close, 26)) * Rank(Std($returns, 20))";

/**
 * Phase 4 of the hybrid agentic-RL rollout — operator surface for
 * AlphaResearcher + StrategyExecutor. Three tabs:
 *
 * 1. Compile — type a symbolic alpha formula and get instant AST
 *    sandbox feedback (operator + field whitelist enforcement).
 * 2. Researcher — drive AlphaResearcher.propose() then evaluate the
 *    proposal end-to-end (compile -> backtest -> reward).
 * 3. Executor — drive StrategyExecutor.decide_and_run() against any
 *    registered RLExperimentSpec; the agent gates on kill-switch
 *    before dispatching the lifecycle action.
 */
export function QuantAgentsRoute() {
  const [tab, setTab] = useState("compile");
  return (
    <PageContainer
      title="Quant agents"
      subtitle="Symbolic alpha researcher + RL strategy executor — Phase 4 of the hybrid agentic-RL rollout."
      extra={
        <Badge variant="default" className="gap-2">
          AgentRuntime + AST sandbox + RLRuntime
        </Badge>
      }
    >
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex flex-wrap">
          <TabsTrigger value="compile">Compile preview</TabsTrigger>
          <TabsTrigger value="researcher">Alpha Researcher</TabsTrigger>
          <TabsTrigger value="executor">Strategy Executor</TabsTrigger>
          <TabsTrigger value="specs">Specs</TabsTrigger>
        </TabsList>
        <TabsContent value="compile" className="mt-3">
          <CompilePreviewPanel />
        </TabsContent>
        <TabsContent value="researcher" className="mt-3">
          <AlphaResearcherPanel />
        </TabsContent>
        <TabsContent value="executor" className="mt-3">
          <StrategyExecutorPanel />
        </TabsContent>
        <TabsContent value="specs" className="mt-3">
          <SpecsPanel />
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}

// ---------------------------------------------------------------------------
// Compile preview
// ---------------------------------------------------------------------------

function CompilePreviewPanel() {
  const [formula, setFormula] = useState(DEFAULT_FORMULA);
  const [name, setName] = useState("ema-crossover-vol-rank");
  const [result, setResult] = useState<FactorCompilePreviewResponse | null>(null);

  const compile = useMutation({
    mutationFn: () => QuantAgentsApi.compilePreview({ formula, name }),
    onSuccess: (data) => {
      setResult(data);
      if (data.ok) {
        toast.success(`Compiled: ${data.used_operators.length} ops, ${data.used_fields.length} fields`);
      } else {
        toast.error(`Compile rejected: ${data.error ?? "unknown"}`);
      }
    },
    onError: (err: Error) => toast.error(`Request failed: ${err.message}`),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Symbolic alpha — AST sandbox preview</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <p className="text-sm text-muted-foreground">
          Type a formula in the AQP DSL. The backend compiles it through the
          AST sandbox (operator / field whitelist) without persisting anything
          — instant feedback on syntax + which operators it touches.
        </p>
        <div className="grid gap-2">
          <Label htmlFor="formula-name">Factor name</Label>
          <Input id="formula-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="formula">Formula</Label>
          <Input
            id="formula"
            className="font-mono"
            value={formula}
            onChange={(e) => setFormula(e.target.value)}
            placeholder="EMA($close, 12) - EMA($close, 26)"
          />
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => compile.mutate()} disabled={compile.isPending}>
            {compile.isPending ? "Compiling..." : "Compile"}
          </Button>
          {result?.ok ? (
            <Badge variant="positive" className="gap-2">
              compiled OK
            </Badge>
          ) : result ? (
            <Badge variant="negative" className="gap-2">
              rejected
            </Badge>
          ) : null}
        </div>
        {result?.ok && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-xs text-muted-foreground">Operators used</div>
              <div className="font-mono">{result.used_operators.join(", ") || "—"}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Fields used</div>
              <div className="font-mono">{result.used_fields.join(", ") || "—"}</div>
            </div>
          </div>
        )}
        {result?.error && (
          <pre className="overflow-auto rounded bg-muted p-3 text-xs text-destructive">{result.error}</pre>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Alpha Researcher
// ---------------------------------------------------------------------------

function AlphaResearcherPanel() {
  const [intent, setIntent] = useState("find a short-horizon mean-reversion factor for high-volatility regimes");
  const [vtSymbol, setVtSymbol] = useState("");
  const [proposal, setProposal] = useState<AlphaProposeResponse | null>(null);
  const [evaluation, setEvaluation] = useState<AlphaEvaluateResponse | null>(null);

  const propose = useMutation({
    mutationFn: () => {
      const payload: { intent: string; vt_symbol?: string } = { intent };
      if (vtSymbol) {
        payload.vt_symbol = vtSymbol;
      }
      return QuantAgentsApi.alphaPropose(payload);
    },
    onSuccess: (data) => {
      setProposal(data);
      setEvaluation(null);
      toast.success(`Proposed: ${data.name}`);
    },
    onError: (err: Error) => toast.error(`Propose failed: ${err.message}`),
  });

  const evaluate = useMutation({
    mutationFn: () => {
      if (!proposal) return Promise.reject(new Error("Propose first"));
      const payload: {
        name: string;
        formula: string;
        rationale: string;
        vt_symbols?: string[];
      } = {
        name: proposal.name,
        formula: proposal.formula,
        rationale: proposal.rationale,
      };
      if (vtSymbol) {
        payload.vt_symbols = [vtSymbol];
      }
      return QuantAgentsApi.alphaEvaluate(payload);
    },
    onSuccess: (data) => {
      setEvaluation(data);
      if (data.compiled) {
        toast.success(`Evaluated: reward=${data.reward.toFixed(4)}`);
      } else {
        toast.error(`Compile rejected: ${data.rejection_reason ?? "unknown"}`);
      }
    },
    onError: (err: Error) => toast.error(`Evaluate failed: ${err.message}`),
  });

  return (
    <div className="grid gap-3">
      <Card>
        <CardHeader>
          <CardTitle>Alpha Researcher — propose</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="grid gap-2">
            <Label htmlFor="intent">Research intent</Label>
            <Input id="intent" value={intent} onChange={(e) => setIntent(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="vt-symbol">VT symbol (optional, e.g. AAPL.NASDAQ)</Label>
            <Input id="vt-symbol" value={vtSymbol} onChange={(e) => setVtSymbol(e.target.value)} className="font-mono" />
          </div>
          <div>
            <Button onClick={() => propose.mutate()} disabled={propose.isPending}>
              {propose.isPending ? "Proposing..." : "Propose factor"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {proposal && (
        <Card>
          <CardHeader>
            <CardTitle>Proposal — {proposal.name}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            <div>
              <div className="text-xs text-muted-foreground">Formula</div>
              <pre className="overflow-auto rounded bg-muted p-3 text-sm">{proposal.formula}</pre>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Rationale</div>
              <p className="text-sm">{proposal.rationale || "—"}</p>
            </div>
            {proposal.expected_direction && (
              <Badge variant="default" className="self-start">
                expected: {proposal.expected_direction}{" "}
                {proposal.expected_horizon_bars ? `over ${proposal.expected_horizon_bars} bars` : ""}
              </Badge>
            )}
            <div>
              <Button onClick={() => evaluate.mutate()} disabled={evaluate.isPending}>
                {evaluate.isPending ? "Evaluating..." : "Compile + backtest"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {evaluation && (
        <Card>
          <CardHeader>
            <CardTitle>Evaluation result</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {evaluation.compiled ? (
                <Badge variant="positive">compiled OK</Badge>
              ) : (
                <Badge variant="negative">rejected: {evaluation.rejection_reason}</Badge>
              )}
              <Badge variant="default">reward = {evaluation.reward.toFixed(4)}</Badge>
            </div>
            <div className="grid grid-cols-4 gap-2 text-sm">
              {Object.entries(evaluation.metrics).map(([k, v]) => (
                <div key={k} className="rounded bg-muted p-2">
                  <div className="text-xs text-muted-foreground">{k}</div>
                  <div className="font-mono">{typeof v === "number" ? v.toFixed(4) : String(v)}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Strategy Executor
// ---------------------------------------------------------------------------

function StrategyExecutorPanel() {
  const [intent, setIntent] = useState<"train" | "evaluate" | "paper" | "replay" | "walk_forward">("evaluate");
  const [slug, setSlug] = useState("ppo-transformer-stock-trading");
  const [checkpoint, setCheckpoint] = useState("");
  const [result, setResult] = useState<StrategyDispatchResponse | null>(null);

  const dispatch = useMutation({
    mutationFn: () =>
      QuantAgentsApi.strategyDispatch({
        intent,
        experiment_slug: slug,
        window: checkpoint ? { checkpoint } : {},
        kill_switch_check: true,
      }),
    onSuccess: (data) => {
      setResult(data);
      if (data.error) {
        toast.error(`Dispatch error: ${data.error}`);
      } else if (data.go) {
        toast.success(`${data.intent} dispatched for ${data.experiment_slug}`);
      } else {
        toast.warning(`Agent declined to proceed: ${data.rationale || data.error || "no rationale"}`);
      }
    },
    onError: (err: Error) => toast.error(`Dispatch failed: ${err.message}`),
  });

  return (
    <div className="grid gap-3">
      <Card>
        <CardHeader>
          <CardTitle>Strategy Executor — dispatch RL lifecycle</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <p className="text-sm text-muted-foreground">
            Routes through <code>StrategyExecutor.decide_and_run</code> → <code>RLRuntime</code> (rule 16).
            The agent gates on the global kill-switch before any paper / live action.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="intent-select">Intent</Label>
              <div className="grid grid-cols-5 gap-1">
                {(["train", "evaluate", "paper", "replay", "walk_forward"] as const).map((opt) => (
                  <Button
                    key={opt}
                    type="button"
                    variant={intent === opt ? "default" : "outline"}
                    size="sm"
                    className="capitalize"
                    onClick={() => setIntent(opt)}
                  >
                    {opt.replace("_", " ")}
                  </Button>
                ))}
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="slug">Experiment slug</Label>
              <Input id="slug" value={slug} onChange={(e) => setSlug(e.target.value)} className="font-mono" />
            </div>
          </div>
          {(intent === "evaluate" || intent === "paper" || intent === "replay") && (
            <div className="grid gap-2">
              <Label htmlFor="checkpoint">Checkpoint path (optional for evaluate; required for paper)</Label>
              <Input
                id="checkpoint"
                value={checkpoint}
                onChange={(e) => setCheckpoint(e.target.value)}
                className="font-mono"
                placeholder="data/models/rl/<run>/policy.zip"
              />
            </div>
          )}
          <div>
            <Button onClick={() => dispatch.mutate()} disabled={dispatch.isPending}>
              {dispatch.isPending ? "Dispatching..." : "Decide + dispatch"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Dispatch result</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={result.go ? "positive" : "warn"}>
                {result.go ? "GO" : "ABORT"}
              </Badge>
              <Badge variant="default">{result.intent}</Badge>
              <Badge variant="outline" className="font-mono">
                {result.experiment_slug}
              </Badge>
            </div>
            {result.rationale && <p className="text-sm">{result.rationale}</p>}
            {result.error && (
              <pre className="overflow-auto rounded bg-destructive/10 p-3 text-xs text-destructive">
                {result.error}
              </pre>
            )}
            {Object.keys(result.runtime_result).length > 0 && (
              <ScrollArea className="max-h-80 rounded border">
                <pre className="overflow-auto p-3 text-xs">{JSON.stringify(result.runtime_result, null, 2)}</pre>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Specs
// ---------------------------------------------------------------------------

function SpecsPanel() {
  const query = useQuery({
    queryKey: ["quant-agents", "specs"],
    queryFn: () => QuantAgentsApi.listSpecs(),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Registered quant-agent specs</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        {query.isLoading && <p className="text-sm text-muted-foreground">Loading specs...</p>}
        {query.isError && <p className="text-sm text-destructive">Failed to load specs.</p>}
        {(query.data ?? []).map((spec) => (
          <div key={spec.name} className="rounded border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold">{spec.name}</h3>
              {spec.role ? <Badge variant="outline">{spec.role}</Badge> : null}
            </div>
            {spec.description ? (
              <p className="mt-2 text-sm">{spec.description}</p>
            ) : null}
            {spec.tools.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1">
                {spec.tools.map((tool) => (
                  <Badge key={tool} variant="default" className="font-mono">
                    {tool}
                  </Badge>
                ))}
              </div>
            ) : null}
            {spec.model?.provider ? (
              <div className="mt-1 text-xs text-muted-foreground">
                model: {String(spec.model.provider ?? "")} {String(spec.model.tier ?? "")}{" "}
                {String(spec.model.model ?? "")}
              </div>
            ) : null}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default QuantAgentsRoute;
