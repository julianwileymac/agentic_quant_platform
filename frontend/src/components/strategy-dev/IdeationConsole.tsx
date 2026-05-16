import { Loader2, MessageSquare, Sparkles } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { CodeEditor } from "@/components/common/CodeEditor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

import { useStrategyDev } from "./StrategyDevLayout";

interface IdeationResponse {
  yaml: string;
  rationale?: string;
  citations?: Array<{ source: string; snippet: string; score?: number }>;
}

const PROMPT_PRESETS = [
  "Pairs trading strategy on cointegrated tech ETFs with volatility-targeting",
  "Sector momentum rotation with dual-momentum filter and TLT safe haven",
  "Volatility risk premium harvester on SPY with delta-neutral hedging",
  "Order-book-imbalance directional alpha on BTC perpetuals",
  "Cross-sectional residual momentum on Russell 1000",
];

/**
 * Read-only LLM ideation console. Routes through `POST /agents/ideate`
 * which hits `router_complete` server-side (AGENTS.md rule 2) and pulls
 * citations from `HierarchicalRAG` including the new `research_papers`
 * corpus. Generated YAML is dropped into the composer with a single
 * click.
 */
export function IdeationConsole() {
  const navigate = useNavigate();
  const { setSelection } = useStrategyDev();
  const [prompt, setPrompt] = useState(PROMPT_PRESETS[0]!);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<IdeationResponse | null>(null);

  const generate = async () => {
    if (!prompt.trim()) {
      toast.warning("Enter an ideation prompt");
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      const res = await apiFetch<IdeationResponse>("/agents/ideate", {
        method: "POST",
        body: JSON.stringify({
          prompt,
          rag_corpora: ["research_papers"],
          rag_orders: ["theory", "first", "second"],
        }),
      });
      setResult(res);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const openInComposer = () => {
    if (!result?.yaml) return;
    setSelection({ composerYaml: result.yaml });
    toast.success("Loaded into composer");
    navigate("/strategy-development/composer");
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4" />
              Ideate a strategy
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-[var(--text-secondary)]">
            LLM-driven ideation. Routes through the canonical{" "}
            <code className="rounded bg-[var(--bg-app)] px-1">router_complete</code> path and grounds
            the response with hits from the research-paper corpus.
          </p>
          <div className="space-y-1">
            <Label htmlFor="ideate-prompt">Prompt</Label>
            <textarea
              id="ideate-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={5}
              className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2 text-sm"
            />
          </div>
          <div className="flex flex-wrap gap-1">
            {PROMPT_PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPrompt(p)}
                className="rounded-full border border-[var(--border-default)] bg-[var(--bg-app)] px-2 py-1 text-[10px] hover:bg-[var(--bg-elevated)]"
              >
                {p.length > 38 ? `${p.slice(0, 38)}…` : p}
              </button>
            ))}
          </div>
          <Button onClick={generate} disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquare className="h-4 w-4" />}
            Generate YAML
          </Button>
        </CardContent>
      </Card>

      <Card className="flex h-full min-h-0 flex-col">
        <CardHeader>
          <CardTitle>Synthesised strategy</CardTitle>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
          {!result ? (
            <p className="text-xs text-[var(--text-secondary)]">
              Generate to see a strategy YAML drafted by the LLM, grounded in retrieved papers.
            </p>
          ) : (
            <>
              {result.rationale ? (
                <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2 text-xs">
                  <div className="mb-1 text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">
                    Rationale
                  </div>
                  <p className="leading-relaxed">{result.rationale}</p>
                </div>
              ) : null}
              <div className="min-h-0 flex-1 overflow-hidden rounded-md">
                <CodeEditor language="json" value={result.yaml} readOnly />
              </div>
              {result.citations?.length ? (
                <div className="space-y-1 text-[10px]">
                  <div className="text-[var(--text-secondary)]">Citations</div>
                  <ul className="flex flex-wrap gap-1">
                    {result.citations.slice(0, 6).map((c, i) => (
                      <li key={i}>
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {c.source}
                          {c.score != null ? ` (${c.score.toFixed(2)})` : ""}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <Button onClick={openInComposer}>
                <Sparkles className="h-4 w-4" />
                Open in composer
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
