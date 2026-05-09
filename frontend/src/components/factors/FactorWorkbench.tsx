import { Loader2, Play } from "lucide-react";
import { useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

interface FactorPrimitive {
  name: string;
  category: string;
  arity: number;
  description: string;
}

interface EvalResult {
  rows: Array<Record<string, unknown>>;
  columns: string[];
  duration_seconds?: number;
  error?: string;
}

export function FactorWorkbench() {
  const primitives = useApiQuery<FactorPrimitive[]>({
    queryKey: ["factors", "primitives"],
    path: "/factors/primitives",
    select: (raw) => (Array.isArray(raw) ? (raw as FactorPrimitive[]) : []),
  });

  const [vtSymbol, setVtSymbol] = useState("AAPL.NASDAQ");
  const [expression, setExpression] = useState("(close - sma(close, 20)) / std(close, 20)");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<EvalResult | null>(null);

  const evaluate = async () => {
    setBusy(true);
    setResult(null);
    try {
      const res = await apiFetch<EvalResult>("/factors/evaluate", {
        method: "POST",
        body: JSON.stringify({ vt_symbol: vtSymbol, expression }),
      });
      setResult(res);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const primCols: ColumnDef<FactorPrimitive>[] = [
    { key: "name", header: "Name", render: (r) => <span className="font-mono">{r.name}</span> },
    { key: "category", header: "Category", width: 130, render: (r) => <Badge variant="secondary">{r.category}</Badge> },
    { key: "arity", header: "Arity", width: 80, align: "right", render: (r) => <span className="font-mono">{r.arity}</span> },
    { key: "description", header: "Description", render: (r) => <span className="text-xs">{r.description}</span> },
  ];

  return (
    <PageContainer
      title="Factor Workbench"
      subtitle="Compose alpha factor expressions using registered primitives. Evaluate against any vt_symbol; the result is a tabular slice of (timestamp, factor)."
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
              <CardTitle>Expression</CardTitle>
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
                <Label>Factor expression</Label>
                <div className="h-32 overflow-hidden rounded-md">
                  <CodeEditor language="python" value={expression} onChange={setExpression} />
                </div>
              </div>
              <Button onClick={evaluate} disabled={busy} className="w-fit gap-2">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {busy ? "Evaluating…" : "Evaluate"}
              </Button>
            </CardContent>
          </Card>

          <Card className="h-[40vh]">
            <CardHeader>
              <CardTitle>Result</CardTitle>
              {result?.duration_seconds ? (
                <Badge variant="secondary">{result.duration_seconds.toFixed(2)}s</Badge>
              ) : null}
            </CardHeader>
            <CardContent className="h-full overflow-auto p-3">
              {!result ? (
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
