import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { AlphaFormulaEditor } from "@/components/strategy-dev/AlphaFormulaEditor";
import { ExampleCard } from "@/components/strategy-dev/ExampleCard";
import { OperatorVocabPanel } from "@/components/strategy-dev/OperatorVocabPanel";
import { PresenceBadge } from "@/components/strategy-dev/PresenceBadge";
import { useStrategyDev } from "@/components/strategy-dev/StrategyDevContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import {
  QuantAgentsApi,
  type AlphaEvaluateResponse,
} from "@/lib/api/quantAgents";
import {
  StrategyLibraryApi,
  type AlphaFormulaTemplate,
  type BundledExample,
  type LibraryHit,
} from "@/lib/api/strategyLibrary";

const DEFAULT_FORMULA = "Sign(EMA($close, 12) - EMA($close, 26)) * Rank(Std($returns, 20))";

/**
 * Phase C — Alpha Factor Studio. Three-column layout:
 *   [ Vocab ] [ Editor + evaluator ] [ Library ]
 *
 * Drives the symbolic-DSL authoring loop end-to-end:
 *   1. User types a formula (or clicks an operator/field token from
 *      the vocab panel, or "Use as template" from a library card).
 *   2. AlphaFormulaEditor auto-compiles via /quant-agents/factor/compile-preview
 *      and surfaces AST sandbox errors inline.
 *   3. Evaluate button calls /quant-agents/alpha-researcher/evaluate
 *      which compiles + backtests on default bars and returns
 *      Sharpe / MDD / turnover / reward.
 *   4. Save button POSTs to /resources with resource_type='alpha_factor'.
 *
 * Deep-link: ?formula=...&name=... prefills the editor (used by the
 * Gallery's "Use as template" button).
 */
export function AlphaFactorStudioRoute() {
  const { selection, setSelection } = useStrategyDev();
  const [params, setParams] = useSearchParams();

  const initialFormula =
    params.get("formula") ||
    selection.alphaFormula ||
    DEFAULT_FORMULA;
  const initialName =
    params.get("name") ||
    selection.alphaFormulaName ||
    "my-alpha";

  const [formula, setFormula] = useState(initialFormula);
  const [name, setName] = useState(initialName);
  const [rationale, setRationale] = useState(selection.alphaRationale ?? "");
  const [evalResult, setEvalResult] = useState<AlphaEvaluateResponse | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [saving, setSaving] = useState(false);
  const editorRef = useRef<HTMLDivElement | null>(null);

  // Clear the deep-link query params after consuming them so a page
  // refresh doesn't keep overwriting the user's edits.
  useEffect(() => {
    if (params.has("formula") || params.has("name")) {
      const next = new URLSearchParams(params);
      next.delete("formula");
      next.delete("name");
      setParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist editor state to StrategyDevContext on debounced change.
  useEffect(() => {
    const id = setTimeout(() => {
      setSelection({
        alphaFormula: formula,
        alphaFormulaName: name,
        alphaRationale: rationale,
      });
    }, 500);
    return () => clearTimeout(id);
  }, [formula, name, rationale, setSelection]);

  const handleInsertToken = (token: string) => {
    setFormula((prev) => (prev.length === 0 || prev.endsWith(" ") ? prev + token : `${prev} ${token}`));
  };

  const handleEvaluate = async () => {
    if (!formula.trim()) {
      toast.warning("Type a formula first");
      return;
    }
    setEvaluating(true);
    try {
      const res = await QuantAgentsApi.alphaEvaluate({
        name,
        formula,
        rationale,
      });
      setEvalResult(res);
      if (res.compiled) {
        toast.success(`reward = ${res.reward.toFixed(4)}`);
      } else {
        toast.error(`Compile rejected: ${res.rejection_reason ?? "unknown"}`);
      }
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    } finally {
      setEvaluating(false);
    }
  };

  const handleSave = async () => {
    if (!formula.trim()) {
      toast.warning("Type a formula first");
      return;
    }
    setSaving(true);
    try {
      const meta: Record<string, unknown> = {
        formula,
        rationale,
      };
      if (evalResult) {
        meta.metrics = evalResult.metrics;
        meta.reward = evalResult.reward;
        meta.compiled = evalResult.compiled;
      }
      const body = {
        name: name.trim() || "my-alpha",
        slug: name.trim() || undefined,
        resource_type: "alpha_factor",
        meta,
        tags: ["alpha_factor", "dsl"],
        visibility: "workspace",
      };
      const created = await apiFetch<{ id: string; name: string }>("/resources", {
        method: "POST",
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" },
      });
      toast.success(`Saved as alpha_factor resource: ${created.name}`);
      // Push into the recent list so the "Recent" library tab picks it up.
      const next = [
        { name: name.trim() || "my-alpha", formula, rationale, savedAt: new Date().toISOString() },
        ...(selection.recentAlphas ?? []),
      ].slice(0, 20);
      setSelection({ recentAlphas: next });
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-[300px_1fr_320px]">
      <OperatorVocabPanel onInsert={handleInsertToken} />

      <Card className="flex h-full min-h-0 flex-col">
        <CardHeader>
          <CardTitle className="flex items-center justify-between gap-2 text-sm">
            <span className="flex items-center gap-2">
              Alpha Factor Studio
              <PresenceBadge displayName={name || "Anonymous"} />
            </span>
            <Badge variant="outline">
              See also: <Link to="/factors" className="underline">classic Factor Workbench</Link>
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex h-full min-h-0 flex-col gap-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_auto]">
            <div className="grid gap-1">
              <Label htmlFor="alpha-name">Factor name</Label>
              <Input
                id="alpha-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-8 font-mono"
              />
            </div>
            <Button
              onClick={handleEvaluate}
              disabled={evaluating || saving}
              className="self-end"
            >
              {evaluating ? "Evaluating..." : "Compile + backtest"}
            </Button>
            <Button
              variant="outline"
              onClick={handleSave}
              disabled={saving || evaluating}
              className="self-end"
            >
              {saving ? "Saving..." : "Save"}
            </Button>
          </div>

          <div ref={editorRef} className="flex h-full min-h-[260px] flex-col gap-2">
            <Label>Formula</Label>
            <AlphaFormulaEditor value={formula} onChange={setFormula} />
          </div>

          <div className="grid gap-1">
            <Label htmlFor="alpha-rationale">Rationale (optional)</Label>
            <textarea
              id="alpha-rationale"
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              rows={3}
              placeholder="Why this factor? What's the trading hypothesis?"
              className="rounded-md border border-[var(--border-default)] bg-transparent p-2 text-xs"
            />
          </div>

          {evalResult ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  Evaluation
                  {evalResult.compiled ? (
                    <Badge variant="positive">compiled</Badge>
                  ) : (
                    <Badge variant="negative">{evalResult.rejection_reason}</Badge>
                  )}
                  <Badge variant="secondary">reward {evalResult.reward.toFixed(4)}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(evalResult.metrics).length > 0 ? (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {Object.entries(evalResult.metrics).map(([k, v]) => (
                      <div key={k} className="rounded bg-[var(--bg-elevated)] p-2">
                        <div className="text-[10px] text-[var(--text-secondary)]">{k}</div>
                        <div className="font-mono text-xs">
                          {typeof v === "number" ? v.toFixed(4) : String(v)}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs italic text-[var(--text-secondary)]">
                    Compiled OK but no bars were loaded for the default universe — pass
                    vt_symbols via the API or seed the DuckDB parquet lake.
                  </p>
                )}
              </CardContent>
            </Card>
          ) : null}
        </CardContent>
      </Card>

      <LibrarySidebar
        recentAlphas={selection.recentAlphas ?? []}
        onUseTemplate={(tpl) => {
          setFormula(tpl.formula);
          setName(tpl.name);
          if (tpl.rationale) setRationale(tpl.rationale);
        }}
      />
    </div>
  );
}

interface LibrarySidebarProps {
  recentAlphas: NonNullable<ReturnType<typeof useStrategyDev>["selection"]["recentAlphas"]>;
  onUseTemplate: (template: AlphaFormulaTemplate) => void;
}

function LibrarySidebar({ recentAlphas, onUseTemplate }: LibrarySidebarProps) {
  const [tab, setTab] = useState("templates");
  return (
    <Card className="flex h-full min-h-0 flex-col">
      <CardHeader>
        <CardTitle className="text-sm">Library</CardTitle>
      </CardHeader>
      <CardContent className="flex h-full min-h-0 flex-col gap-2 overflow-hidden">
        <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-0 flex-col">
          <TabsList className="w-full">
            <TabsTrigger value="templates" className="flex-1">
              Templates
            </TabsTrigger>
            <TabsTrigger value="alpha-base" className="flex-1">
              Alpha base
            </TabsTrigger>
            <TabsTrigger value="recent" className="flex-1">
              Recent
            </TabsTrigger>
          </TabsList>
          <TabsContent value="templates" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full pr-2">
              <TemplatesList onUseTemplate={onUseTemplate} />
            </ScrollArea>
          </TabsContent>
          <TabsContent value="alpha-base" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full pr-2">
              <AlphaBaseList onUseTemplate={onUseTemplate} />
            </ScrollArea>
          </TabsContent>
          <TabsContent value="recent" className="flex-1 overflow-hidden">
            <ScrollArea className="h-full pr-2">
              <RecentList
                recents={recentAlphas}
                onUseTemplate={(r) =>
                  onUseTemplate({
                    name: r.name,
                    formula: r.formula,
                    rationale: r.rationale ?? "",
                    tags: [],
                  })
                }
              />
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function TemplatesList({ onUseTemplate }: { onUseTemplate: (t: AlphaFormulaTemplate) => void }) {
  const q = useQuery({
    queryKey: ["alpha-templates"],
    queryFn: () => StrategyLibraryApi.alphaTemplates(),
  });
  if (q.isLoading) return <p className="text-xs text-[var(--text-secondary)]">Loading...</p>;
  if (q.isError) return <p className="text-xs text-[var(--neg-fg)]">Failed to load.</p>;
  const items = q.data?.items ?? [];
  return (
    <div className="grid gap-2">
      {items.map((tpl) => (
        <TemplateCard key={tpl.name} template={tpl} onUseTemplate={onUseTemplate} />
      ))}
    </div>
  );
}

function TemplateCard({
  template,
  onUseTemplate,
}: {
  template: AlphaFormulaTemplate;
  onUseTemplate: (t: AlphaFormulaTemplate) => void;
}) {
  const example: BundledExample = useMemo(
    () => ({
      kind: "alpha_factor",
      name: template.name,
      slug: template.name,
      description: template.rationale.split("\n", 1)[0] ?? null,
      source_path: null,
      payload: template as unknown as Record<string, unknown>,
      tags: template.tags,
    }),
    [template],
  );

  return (
    <div className="grid gap-1 rounded border border-[var(--border-default)] p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-xs">{template.name}</span>
        <Button size="sm" variant="outline" onClick={() => onUseTemplate(template)}>
          Use
        </Button>
      </div>
      <code className="block truncate text-[10px] text-[var(--text-secondary)]">{template.formula}</code>
      {template.tags.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {template.tags.slice(0, 4).map((tag) => (
            <Badge key={tag} variant="outline" className="font-mono text-[9px]">
              {tag}
            </Badge>
          ))}
        </div>
      ) : null}
      {/* keep ExampleCard reachable for richer flows from /gallery */}
      <div className="hidden">
        <ExampleCard example={example} />
      </div>
    </div>
  );
}

function AlphaBaseList({ onUseTemplate }: { onUseTemplate: (t: AlphaFormulaTemplate) => void }) {
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(id);
  }, [q]);
  const query = useQuery({
    queryKey: ["alpha-base-rag", debouncedQ],
    queryFn: () => StrategyLibraryApi.libraryQuery("alpha_factors", debouncedQ, 12),
  });
  return (
    <div className="grid gap-2">
      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search alpha base..."
        className="h-8"
      />
      {query.isLoading ? (
        <p className="text-xs text-[var(--text-secondary)]">Loading...</p>
      ) : query.isError ? (
        <p className="text-xs text-[var(--neg-fg)]">Search failed.</p>
      ) : (query.data?.items ?? []).length === 0 ? (
        <p className="text-xs italic text-[var(--text-secondary)]">
          No hits yet. Save alpha factors via the Studio + run the RAG indexer to populate this corpus.
        </p>
      ) : (
        (query.data?.items ?? []).map((hit) => (
          <RAGHitCard key={hit.doc_id} hit={hit} onUseTemplate={onUseTemplate} />
        ))
      )}
    </div>
  );
}

function RAGHitCard({
  hit,
  onUseTemplate,
}: {
  hit: LibraryHit;
  onUseTemplate: (t: AlphaFormulaTemplate) => void;
}) {
  const formula = String(hit.meta.formula ?? "");
  const name = String(hit.meta.name ?? hit.doc_id);
  const rationale = String(hit.meta.rationale ?? "");
  return (
    <div className="grid gap-1 rounded border border-[var(--border-default)] p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-xs">{name}</span>
        <Badge variant="secondary">score {hit.score.toFixed(2)}</Badge>
      </div>
      <code className="block truncate text-[10px] text-[var(--text-secondary)]">{formula}</code>
      <Button
        size="sm"
        variant="outline"
        disabled={!formula}
        onClick={() => onUseTemplate({ name, formula, rationale, tags: [] })}
      >
        Use as template
      </Button>
    </div>
  );
}

function RecentList({
  recents,
  onUseTemplate,
}: {
  recents: NonNullable<ReturnType<typeof useStrategyDev>["selection"]["recentAlphas"]>;
  onUseTemplate: (r: { name: string; formula: string; rationale?: string; savedAt: string }) => void;
}) {
  if (recents.length === 0) {
    return (
      <p className="text-xs italic text-[var(--text-secondary)]">
        No recent alphas yet. Save one to pin it here.
      </p>
    );
  }
  return (
    <div className="grid gap-2">
      {recents.map((r) => (
        <div key={`${r.name}-${r.savedAt}`} className="grid gap-1 rounded border border-[var(--border-default)] p-2">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-mono text-xs">{r.name}</span>
            <Badge variant="outline" className="font-mono text-[9px]">
              {new Date(r.savedAt).toLocaleString()}
            </Badge>
          </div>
          <code className="block truncate text-[10px] text-[var(--text-secondary)]">{r.formula}</code>
          <Button size="sm" variant="outline" onClick={() => onUseTemplate(r)}>
            Use
          </Button>
        </div>
      ))}
    </div>
  );
}
