import { ArrowRight, ExternalLink, Loader2, Play, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { CodeEditor } from "@/components/common/CodeEditor";
import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import {
  QuantAgentsApi,
  type FactorCompilePreviewResponse,
} from "@/lib/api/quantAgents";

interface FactorPrimitive {
  name: string;
  category: string;
  arity: number;
  description: string;
}

interface EvalResult {
  rows: Array<Record<string, unknown>>;
  columns?: string[];
  summary?: Record<string, unknown>;
  n_rows?: number;
  n_symbols?: number;
  duration_seconds?: number;
  error?: string;
}

type FactorMode = "legacy" | "symbolic";

const LEGACY_DEFAULT = "(close - Mean(close, 20)) / Std(close, 20)";
const SYMBOLIC_DEFAULT =
  "Sign(EMA($close, 12) - EMA($close, 26)) * Rank(Std($returns, 20))";

/**
 * Unified Factor Workbench. Out-of-scope item from the
 * hybrid-agentic-rl-quant plan: the original workbench only spoke
 * the legacy ``aqp/data/expressions.py`` DSL. We now expose a mode
 * toggle that lets users author the same kind of factor in either:
 *   - Legacy DSL  -> `/factors/preview` (raw column names like `close`).
 *   - Symbolic DSL -> `/quant-agents/factor/compile-preview`
 *     (AST-sandboxed `$close` tokens; same compiler the
 *     AlphaResearcher agent uses, AGENTS.md rule 39).
 *
 * Symbolic mode surfaces a "Open in Alpha Factor Studio" deep-link
 * so users can graduate from a quick ad-hoc preview into the full
 * save / evaluate / library loop without retyping the formula.
 */
export function FactorWorkbench() {
  const [mode, setMode] = useState<FactorMode>("symbolic");
  const [vtSymbol, setVtSymbol] = useState("AAPL.NASDAQ");
  const [expression, setExpression] = useState(SYMBOLIC_DEFAULT);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<EvalResult | null>(null);
  const [compilePreview, setCompilePreview] =
    useState<FactorCompilePreviewResponse | null>(null);
  const compileTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const primitives = useApiQuery<FactorPrimitive[]>({
    queryKey: ["factors", "operators"],
    path: "/factors/operators",
    select: (raw) => (Array.isArray(raw) ? (raw as FactorPrimitive[]) : []),
  });

  useEffect(() => {
    if (compileTimerRef.current) clearTimeout(compileTimerRef.current);
    if (mode !== "symbolic") {
      setCompilePreview(null);
      return;
    }
    const trimmed = expression.trim();
    if (!trimmed) {
      setCompilePreview(null);
      return;
    }
    compileTimerRef.current = setTimeout(() => {
      QuantAgentsApi.compilePreview({ formula: trimmed })
        .then((res) => setCompilePreview(res))
        .catch((err) =>
          setCompilePreview({
            ok: false,
            formula: trimmed,
            used_operators: [],
            used_fields: [],
            error: err instanceof Error ? err.message : String(err),
          }),
        );
    }, 400);
    return () => {
      if (compileTimerRef.current) clearTimeout(compileTimerRef.current);
    };
  }, [expression, mode]);

  const handleModeChange = (value: string) => {
    const next = value as FactorMode;
    setMode(next);
    setResult(null);
    setCompilePreview(null);
    setExpression(next === "symbolic" ? SYMBOLIC_DEFAULT : LEGACY_DEFAULT);
  };

  const evaluate = async () => {
    setBusy(true);
    setResult(null);
    try {
      if (mode === "legacy") {
        const res = await apiFetch<EvalResult>("/factors/preview", {
          method: "POST",
          body: JSON.stringify({
            symbols: [vtSymbol],
            formula: expression,
            rows: 50,
          }),
        });
        setResult(res);
        return;
      }
      // Symbolic mode runs the compile-preview synchronously to
      // surface operator/field usage. Full backtest evaluation lives
      // in the Alpha Factor Studio (which calls
      // /quant-agents/alpha-researcher/evaluate).
      const compiled = await QuantAgentsApi.compilePreview({ formula: expression });
      setCompilePreview(compiled);
      if (compiled.ok) {
        toast.success("Formula compiled");
      } else {
        toast.error(`Compile rejected: ${compiled.error ?? "unknown"}`);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const studioHref = useMemo(() => {
    const params = new URLSearchParams({ formula: expression, name: "workbench-clone" });
    return `/strategy-development/alpha-factors?${params.toString()}`;
  }, [expression]);

  const primCols: ColumnDef<FactorPrimitive>[] = [
    { key: "name", header: "Name", render: (r) => <span className="font-mono">{r.name}</span> },
    { key: "category", header: "Category", width: 130, render: (r) => <Badge variant="secondary">{r.category}</Badge> },
    { key: "arity", header: "Arity", width: 80, align: "right", render: (r) => <span className="font-mono">{r.arity}</span> },
    { key: "description", header: "Description", render: (r) => <span className="text-xs">{r.description}</span> },
  ];

  return (
    <PageContainer
      title="Factor Workbench"
      subtitle="Compose alpha factor expressions in either the legacy DSL or the AST-sandboxed symbolic DSL. Evaluate against any vt_symbol; the symbolic mode shares its compiler with the AlphaResearcher agent."
      extra={
        <Tabs value={mode} onValueChange={handleModeChange}>
          <TabsList>
            <TabsTrigger value="symbolic" className="gap-1">
              <ShieldCheck className="h-3 w-3" /> Symbolic DSL
            </TabsTrigger>
            <TabsTrigger value="legacy">Legacy DSL</TabsTrigger>
          </TabsList>
        </Tabs>
      }
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[420px_1fr]">
        <Card className="h-[60vh]">
          <CardHeader>
            <CardTitle>Primitives</CardTitle>
            <Badge variant="secondary">{primitives.data?.length ?? 0}</Badge>
          </CardHeader>
          <CardContent className="h-full p-0">
            <DataTable<FactorPrimitive>
              rows={primitives.data ?? []}
              rowKey={(r) => r.name}
              columns={primCols}
              emptyState={
                primitives.isPending ? <span>Loading…</span> : <span>No primitives registered.</span>
              }
            />
          </CardContent>
        </Card>

        <div className="flex flex-col gap-3">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Expression
                {mode === "symbolic" ? (
                  <Badge variant="positive" className="gap-1">
                    <ShieldCheck className="h-3 w-3" /> AST sandbox
                  </Badge>
                ) : (
                  <Badge variant="outline">legacy / unguarded</Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <div className="flex flex-col gap-1">
                <Label htmlFor="vt">vt_symbol</Label>
                <Input
                  id="vt"
                  value={vtSymbol}
                  onChange={(e) => setVtSymbol(e.target.value)}
                  className="max-w-sm font-mono"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label>
                  Factor expression{" "}
                  <span className="text-[10px] text-[var(--text-secondary)]">
                    {mode === "symbolic"
                      ? "use $close / $open / $high / $low / $volume / $vwap / $returns"
                      : "use raw column names: close, open, high, low, volume"}
                  </span>
                </Label>
                <div className="h-32 overflow-hidden rounded-md">
                  <CodeEditor language="python" value={expression} onChange={setExpression} />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={evaluate} disabled={busy} className="gap-2">
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  {busy ? "Evaluating…" : mode === "symbolic" ? "Compile" : "Evaluate"}
                </Button>
                {mode === "symbolic" ? (
                  <Button asChild variant="outline" className="gap-2">
                    <Link to={studioHref}>
                      Open in Alpha Factor Studio <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                ) : (
                  <Button asChild variant="ghost" className="gap-2">
                    <a
                      href="/factors/operators"
                      target="_blank"
                      rel="noreferrer"
                    >
                      View raw operator catalog <ExternalLink className="h-4 w-4" />
                    </a>
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {mode === "symbolic" && compilePreview ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  Compile preview
                  {compilePreview.ok ? (
                    <Badge variant="positive">OK</Badge>
                  ) : (
                    <Badge variant="negative">rejected</Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-2 text-xs">
                {compilePreview.ok ? (
                  <>
                    <p>
                      <span className="text-[var(--text-secondary)]">operators:</span>{" "}
                      <span className="font-mono">
                        {compilePreview.used_operators.join(", ") || "—"}
                      </span>
                    </p>
                    <p>
                      <span className="text-[var(--text-secondary)]">fields:</span>{" "}
                      <span className="font-mono">
                        {compilePreview.used_fields.join(", ") || "—"}
                      </span>
                    </p>
                  </>
                ) : (
                  <pre className="overflow-auto whitespace-pre-wrap text-[var(--neg-fg)]">
                    {compilePreview.error ?? "unknown error"}
                  </pre>
                )}
              </CardContent>
            </Card>
          ) : null}

          <Card className="h-[40vh]">
            <CardHeader>
              <CardTitle>Result</CardTitle>
              {result?.duration_seconds ? (
                <Badge variant="secondary">{result.duration_seconds.toFixed(2)}s</Badge>
              ) : null}
            </CardHeader>
            <CardContent className="h-full overflow-auto p-3">
              {mode === "symbolic" && !result ? (
                <p className="text-sm italic text-[var(--text-secondary)]">
                  Symbolic mode only previews the AST sandbox here. For a full
                  backtest evaluation (Sharpe / MDD / turnover / reward) jump
                  into the Alpha Factor Studio via the button above.
                </p>
              ) : !result ? (
                <p className="text-sm italic text-[var(--text-secondary)]">
                  Evaluate to see (timestamp, factor) rows.
                </p>
              ) : result.error ? (
                <p className="text-sm text-[var(--neg-fg)]">{result.error}</p>
              ) : (
                <pre className="overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs">
                  {JSON.stringify(result.rows.slice(0, 50), null, 2)}
                </pre>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}
