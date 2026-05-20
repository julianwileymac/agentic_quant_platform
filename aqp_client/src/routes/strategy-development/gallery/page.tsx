import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ExampleCard } from "@/components/strategy-dev/ExampleCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  StrategyLibraryApi,
  type BundledExample,
  type LibraryCorpus,
  type LibraryHit,
} from "@/lib/api/strategyLibrary";

const CORPUS_TABS: ReadonlyArray<{
  id: LibraryCorpus;
  label: string;
  description: string;
}> = [
  {
    id: "alpha_factors",
    label: "Alpha factors (RAG)",
    description: "Saved alpha factor formulas + their measured metrics",
  },
  {
    id: "backtest_summaries",
    label: "Backtest summaries (RAG)",
    description: "Indexed run summaries (Sharpe, MDD, turnover)",
  },
  {
    id: "rl_trajectory_summaries",
    label: "RL trajectories (RAG)",
    description: "Aggregate RL run summaries from rl.trajectories",
  },
];

/**
 * Phase F — Unified Examples Library / Gallery.
 *
 * Tabs:
 *   - Bundled: union of /quant-agents/examples (alpha formulas +
 *     RL specs + agent specs, grouped by kind).
 *   - 3 RAG tabs: one per Phase 7 alpha-base corpus
 *     (alpha_factors / backtest_summaries / rl_trajectory_summaries).
 *
 * Every card uses the `ExampleCard` primitive whose "Use as template"
 * button routes to the matching studio with the right deep-link.
 */
export function GalleryRoute() {
  const [tab, setTab] = useState("bundled");
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Examples Gallery</CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-[var(--text-secondary)]">
          Bundled examples ship with the platform and reside under{" "}
          <code>configs/</code>. RAG tabs query the alpha-base corpora
          populated by the indexer pipeline — they grow as you save
          alpha factors, complete backtests, and finish RL runs.
        </CardContent>
      </Card>

      <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-0 flex-col">
        <TabsList>
          <TabsTrigger value="bundled">Bundled</TabsTrigger>
          {CORPUS_TABS.map((c) => (
            <TabsTrigger key={c.id} value={c.id}>
              {c.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="bundled" className="min-h-0 flex-1">
          <BundledTab />
        </TabsContent>
        {CORPUS_TABS.map((c) => (
          <TabsContent key={c.id} value={c.id} className="min-h-0 flex-1">
            <RAGTab corpus={c.id} description={c.description} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

function BundledTab() {
  const query = useQuery({
    queryKey: ["gallery", "examples"],
    queryFn: () => StrategyLibraryApi.examples(),
  });
  const items = query.data?.items ?? [];
  const groups = useMemo(() => {
    const buckets: Record<BundledExample["kind"], BundledExample[]> = {
      alpha_factor: [],
      rl_spec: [],
      agent_spec: [],
    };
    for (const item of items) {
      buckets[item.kind].push(item);
    }
    return buckets;
  }, [items]);

  if (query.isLoading)
    return <p className="text-xs text-[var(--text-secondary)]">Loading examples...</p>;
  if (query.isError)
    return <p className="text-xs text-[var(--neg-fg)]">Failed to load /quant-agents/examples.</p>;

  return (
    <ScrollArea className="h-full pr-2">
      <div className="grid gap-4">
        <Section
          title="Alpha formulas"
          count={groups.alpha_factor.length}
          description="Curated symbolic-DSL templates. 'Use as template' opens the Alpha Factor Studio with the formula prefilled."
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {groups.alpha_factor.map((ex) => (
              <ExampleCard key={ex.slug} example={ex} showSourcePath />
            ))}
          </div>
        </Section>
        <Section
          title="RL experiment specs"
          count={groups.rl_spec.length}
          description="Bundled RLExperimentSpec YAMLs under configs/rl/policies/. 'Use as template' hydrates the RL Lab meta panel."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {groups.rl_spec.map((ex) => (
              <ExampleCard key={ex.slug} example={ex} showSourcePath />
            ))}
          </div>
        </Section>
        <Section
          title="Quant agent specs"
          count={groups.agent_spec.length}
          description="The AlphaResearcher + StrategyExecutor agent specs (AGENTS.md rule 12)."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {groups.agent_spec.map((ex) => (
              <ExampleCard key={ex.slug} example={ex} showSourcePath />
            ))}
          </div>
        </Section>
      </div>
    </ScrollArea>
  );
}

function RAGTab({ corpus, description }: { corpus: LibraryCorpus; description: string }) {
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(id);
  }, [q]);

  const query = useQuery({
    queryKey: ["gallery", "rag", corpus, debouncedQ],
    queryFn: () => StrategyLibraryApi.libraryQuery(corpus, debouncedQ, 24),
  });

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <Card>
        <CardContent className="grid gap-2 py-2">
          <p className="text-xs text-[var(--text-secondary)]">{description}</p>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-[var(--text-secondary)]" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by semantic meaning (free text)..."
              className="h-8 pl-7"
            />
          </div>
        </CardContent>
      </Card>
      <ScrollArea className="h-full pr-2">
        {query.isLoading ? (
          <p className="text-xs text-[var(--text-secondary)]">Loading...</p>
        ) : query.isError ? (
          <p className="text-xs text-[var(--neg-fg)]">RAG query failed.</p>
        ) : (query.data?.items ?? []).length === 0 ? (
          <EmptyCorpusBanner corpus={corpus} />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {(query.data?.items ?? []).map((hit) => (
              <RAGHitCard key={hit.doc_id} hit={hit} corpus={corpus} />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

function RAGHitCard({ hit, corpus }: { hit: LibraryHit; corpus: LibraryCorpus }) {
  // Best-effort coerce the corpus hit into a BundledExample so we can
  // reuse ExampleCard's "Use as template" logic. The kind mapping is:
  //   - alpha_factors -> alpha_factor (uses the meta.formula)
  //   - rl_trajectory_summaries -> rl_spec (uses the meta.rl_experiment_slug)
  //   - backtest_summaries -> alpha_factor (most common backtests are
  //     alpha-factor runs); fall back to "rl_spec" if rl_run_id present.
  const meta = hit.meta as Record<string, unknown>;
  let example: BundledExample;
  if (corpus === "alpha_factors") {
    example = {
      kind: "alpha_factor",
      name: String(meta.name ?? hit.doc_id),
      slug: String(meta.slug ?? meta.name ?? hit.doc_id),
      description: hit.text.slice(0, 240),
      source_path: null,
      payload: {
        name: String(meta.name ?? hit.doc_id),
        formula: String(meta.formula ?? ""),
        rationale: String(meta.rationale ?? ""),
      },
      tags: Array.isArray(meta.tags) ? (meta.tags as string[]) : [],
    };
  } else if (corpus === "rl_trajectory_summaries" || meta.rl_experiment_slug) {
    example = {
      kind: "rl_spec",
      name: String(meta.name ?? meta.rl_experiment_slug ?? hit.doc_id),
      slug: String(meta.slug ?? meta.rl_experiment_slug ?? hit.doc_id),
      description: hit.text.slice(0, 240),
      source_path: null,
      payload: { ...meta },
      tags: Array.isArray(meta.tags) ? (meta.tags as string[]) : [],
    };
  } else {
    // Backtest summary — coerce to alpha_factor template so the user
    // can pull the formula straight into the Alpha Factor Studio.
    example = {
      kind: "alpha_factor",
      name: String(meta.name ?? hit.doc_id),
      slug: String(meta.slug ?? meta.name ?? hit.doc_id),
      description: hit.text.slice(0, 240),
      source_path: null,
      payload: {
        name: String(meta.name ?? hit.doc_id),
        formula: String(meta.formula ?? ""),
        rationale: String(meta.rationale ?? ""),
      },
      tags: Array.isArray(meta.tags) ? (meta.tags as string[]) : [],
    };
  }

  const kpis: Array<{ label: string; value: string | number }> = [];
  for (const key of ["sharpe", "max_drawdown", "turnover", "total_return"]) {
    const v = meta[key];
    if (typeof v === "number") {
      kpis.push({
        label: key,
        value: Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(3),
      });
    }
  }
  if (kpis.length === 0 && typeof meta.reward === "number") {
    kpis.push({ label: "reward", value: (meta.reward as number).toFixed(3) });
  }

  return (
    <div className="grid gap-1">
      <ExampleCard example={example} kpis={kpis} />
      <div className="flex items-center gap-1 px-1">
        <Badge variant="outline" className="font-mono text-[9px]">
          score {hit.score.toFixed(2)}
        </Badge>
        {hit.vt_symbol ? (
          <Badge variant="outline" className="font-mono text-[9px]">
            {hit.vt_symbol}
          </Badge>
        ) : null}
        {hit.as_of ? (
          <Badge variant="outline" className="font-mono text-[9px]">
            {hit.as_of}
          </Badge>
        ) : null}
      </div>
    </div>
  );
}

function EmptyCorpusBanner({ corpus }: { corpus: LibraryCorpus }) {
  const text = {
    alpha_factors:
      "No alpha factors indexed yet. Save formulas via the Alpha Factor Studio and run the indexer pipeline to populate this corpus.",
    backtest_summaries:
      "No backtest summaries indexed yet. Run backtests + trigger the indexer pipeline.",
    rl_trajectory_summaries:
      "No RL trajectory summaries indexed yet. Run RL experiments via the RL Lab + trigger the indexer pipeline.",
  }[corpus];
  return (
    <Card>
      <CardContent className="py-6 text-center text-xs italic text-[var(--text-secondary)]">
        {text}
      </CardContent>
    </Card>
  );
}

function Section({
  title,
  count,
  description,
  children,
}: {
  title: string;
  count: number;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          <p className="text-xs text-[var(--text-secondary)]">{description}</p>
        </div>
        <Badge variant="outline">{count}</Badge>
      </div>
      {children}
    </div>
  );
}
