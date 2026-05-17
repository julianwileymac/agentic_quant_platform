import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Github, RefreshCw, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { StrategyLibraryApi, type BundledExample } from "@/lib/api/strategyLibrary";

const GITHUB_REPO_ROOT = "https://github.com/julianwiley/agentic_quant_platform/blob/main";

const ALPHA_BASE_CORPORA: ReadonlyArray<{ id: string; label: string; description: string }> = [
  {
    id: "alpha_factors",
    label: "alpha_factors",
    description: "Persisted symbolic alpha factor formulas (resource_type=alpha_factor)",
  },
  {
    id: "backtest_summaries",
    label: "backtest_summaries",
    description: "Per-run backtest summary cards (Sharpe / MDD / turnover)",
  },
  {
    id: "rl_trajectory_summaries",
    label: "rl_trajectory_summaries",
    description: "Aggregate RL run summaries pulled from rl.trajectories",
  },
];

interface RagCorpusInfo {
  name: string;
  order: string;
  l1: string;
  l2: string;
  iceberg?: string;
  description: string;
  chunks: number;
}

/**
 * OOS extension — Library Admin surface.
 *
 * Read-only management view for bundled examples + alpha-base RAG
 * corpora. Bundled YAMLs are file-backed (edit-via-GitHub only —
 * the plan's "library admin is OOS because bundled examples are
 * git-driven" still holds for editing). What changed: we surface
 * RAG corpus stats + a one-click reindex button so the indexer
 * pipeline isn't hidden behind the CLI.
 */
export function LibraryAdminRoute() {
  const [tab, setTab] = useState("bundled");
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Library admin</CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-[var(--text-secondary)]">
          Bundled examples are file-backed under <code>configs/</code> — to
          add / edit a template, open a pull request. The Alpha-base RAG
          corpora populate via the indexer pipeline; trigger a re-index
          below to refresh the gallery results.
        </CardContent>
      </Card>

      <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-0 flex-col">
        <TabsList>
          <TabsTrigger value="bundled">Bundled examples</TabsTrigger>
          <TabsTrigger value="rag">RAG corpora</TabsTrigger>
        </TabsList>
        <TabsContent value="bundled" className="min-h-0 flex-1">
          <BundledExamplesAdmin />
        </TabsContent>
        <TabsContent value="rag" className="min-h-0 flex-1">
          <RagCorporaAdmin />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function BundledExamplesAdmin() {
  const query = useQuery({
    queryKey: ["library-admin", "examples"],
    queryFn: () => StrategyLibraryApi.examples(),
  });
  const groups = useMemo(() => {
    const items = query.data?.items ?? [];
    const buckets: Record<BundledExample["kind"], BundledExample[]> = {
      alpha_factor: [],
      rl_spec: [],
      agent_spec: [],
    };
    for (const item of items) {
      buckets[item.kind].push(item);
    }
    return buckets;
  }, [query.data]);

  if (query.isLoading)
    return <p className="text-xs text-[var(--text-secondary)]">Loading bundled examples...</p>;
  if (query.isError)
    return <p className="text-xs text-[var(--neg-fg)]">Failed to load bundled examples.</p>;

  return (
    <ScrollArea className="h-full pr-2">
      <div className="grid gap-3">
        <BundledGroup
          title="Alpha formulas"
          items={groups.alpha_factor}
          emptyHint="Add entries to configs/strategies/alpha_factor_templates.yaml"
        />
        <BundledGroup
          title="RL experiment specs"
          items={groups.rl_spec}
          emptyHint="Add YAML files under configs/rl/policies/"
        />
        <BundledGroup
          title="Quant agent specs"
          items={groups.agent_spec}
          emptyHint="Add YAML files under configs/agents/"
        />
      </div>
    </ScrollArea>
  );
}

function BundledGroup({
  title,
  items,
  emptyHint,
}: {
  title: string;
  items: BundledExample[];
  emptyHint: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2 text-sm">
          <span>{title}</span>
          <Badge variant="outline">{items.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2">
        {items.length === 0 ? (
          <p className="text-xs italic text-[var(--text-secondary)]">{emptyHint}</p>
        ) : (
          items.map((it) => (
            <div
              key={it.slug}
              className="grid items-center gap-2 rounded border border-[var(--border-default)] p-2 sm:grid-cols-[1fr_auto]"
            >
              <div>
                <div className="flex items-center gap-2">
                  <Sparkles className="h-3 w-3 text-[var(--text-secondary)]" />
                  <span className="truncate font-mono text-xs">{it.name}</span>
                  <Badge variant="secondary" className="text-[9px]">
                    {it.kind.replace("_", " ")}
                  </Badge>
                </div>
                {it.description ? (
                  <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{it.description}</p>
                ) : null}
                {it.source_path ? (
                  <code className="block truncate text-[10px] text-[var(--text-secondary)]">
                    {it.source_path}
                  </code>
                ) : null}
              </div>
              {it.source_path ? (
                <Button asChild variant="outline" size="sm" className="gap-1">
                  <a
                    href={`${GITHUB_REPO_ROOT}/${it.source_path.replace(/^\/?app\//, "")}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Github className="h-3 w-3" /> Edit on GitHub
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </Button>
              ) : null}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function RagCorporaAdmin() {
  const qc = useQueryClient();
  const corpora = useQuery<RagCorpusInfo[]>({
    queryKey: ["rag", "corpora"],
    queryFn: () => apiFetch<RagCorpusInfo[]>("/rag/corpora"),
  });
  const reindex = useMutation({
    mutationFn: (corpus: string) =>
      apiFetch<{ task_id: string; stream_url?: string }>(
        `/rag/index/${encodeURIComponent(corpus)}`,
        { method: "POST", body: "{}" },
      ),
    onSuccess: (res, corpus) => {
      toast.success(`Re-index queued: ${corpus} (task ${res.task_id})`);
      qc.invalidateQueries({ queryKey: ["rag", "corpora"] });
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    },
  });

  if (corpora.isLoading)
    return <p className="text-xs text-[var(--text-secondary)]">Loading corpora...</p>;
  if (corpora.isError)
    return <p className="text-xs text-[var(--neg-fg)]">Failed to load /rag/corpora.</p>;

  const all = corpora.data ?? [];
  const alphaBase = all.filter((c) =>
    ALPHA_BASE_CORPORA.some((meta) => meta.id === c.name),
  );
  const other = all.filter((c) => !alphaBase.some((a) => a.name === c.name));

  return (
    <ScrollArea className="h-full pr-2">
      <div className="grid gap-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Alpha-base corpora (Phase 7)</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {ALPHA_BASE_CORPORA.map((meta) => {
              const live = alphaBase.find((c) => c.name === meta.id);
              return (
                <CorpusRow
                  key={meta.id}
                  name={meta.id}
                  label={meta.label}
                  description={meta.description}
                  chunks={live?.chunks ?? 0}
                  order={live?.order ?? "—"}
                  l1={live?.l1 ?? "—"}
                  l2={live?.l2 ?? "—"}
                  registered={Boolean(live)}
                  onReindex={() => reindex.mutate(meta.id)}
                  busy={reindex.isPending && reindex.variables === meta.id}
                />
              );
            })}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">All RAG corpora ({all.length})</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {other.length === 0 ? (
              <p className="text-xs italic text-[var(--text-secondary)]">
                Only alpha-base corpora registered.
              </p>
            ) : (
              other.map((c) => (
                <CorpusRow
                  key={c.name}
                  name={c.name}
                  label={c.name}
                  description={c.description || `${c.order} / ${c.l1} / ${c.l2}`}
                  chunks={c.chunks}
                  order={c.order}
                  l1={c.l1}
                  l2={c.l2}
                  registered
                  onReindex={() => reindex.mutate(c.name)}
                  busy={reindex.isPending && reindex.variables === c.name}
                />
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  );
}

function CorpusRow({
  label,
  description,
  chunks,
  order,
  l1,
  l2,
  registered,
  onReindex,
  busy,
}: {
  name: string;
  label: string;
  description: string;
  chunks: number;
  order: string;
  l1: string;
  l2: string;
  registered: boolean;
  onReindex: () => void;
  busy: boolean;
}) {
  return (
    <div className="grid items-start gap-2 rounded border border-[var(--border-default)] p-2 sm:grid-cols-[1fr_auto]">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs">{label}</span>
          {registered ? (
            <Badge variant="secondary" className="text-[9px]">
              {chunks} chunks
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[9px]">
              not registered
            </Badge>
          )}
          <Badge variant="outline" className="font-mono text-[9px]">
            {order} / {l1} / {l2}
          </Badge>
        </div>
        {description ? (
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{description}</p>
        ) : null}
      </div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={onReindex}
        disabled={busy || !registered}
        className="gap-1"
        title={!registered ? "Corpus not registered — nothing to re-index" : undefined}
      >
        {busy ? "Queuing..." : "Re-index"}{" "}
        <RefreshCw className={busy ? "h-3 w-3 animate-spin" : "h-3 w-3"} />
      </Button>
    </div>
  );
}
