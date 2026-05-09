import { GitBranch, Network, RefreshCcw, Sparkles } from "lucide-react";
import { useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { ProgressTimeline } from "@/components/common/ProgressTimeline";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { ragApi, type RagCorpusInfo } from "@/lib/api/rag";
import { useChatStream } from "@/lib/ws";
import { formatTime } from "@/lib/utils";

type ActionKind =
  | { kind: "refreshL0" }
  | { kind: "refreshHierarchy" }
  | { kind: "indexCorpus"; corpus: string }
  | { kind: "raptor"; corpus: string };

export function RagAdminRoute() {
  const [pending, setPending] = useState<ActionKind | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const stream = useChatStream(activeTaskId, "chat");

  const corpora = useApiQuery<RagCorpusInfo[]>({
    queryKey: ["rag", "corpora"],
    path: "/rag/corpora",
    refetchInterval: 30_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const submit = async () => {
    if (!pending) return;
    try {
      let result: { task_id: string };
      switch (pending.kind) {
        case "refreshL0":
          result = await ragApi.refreshL0();
          break;
        case "refreshHierarchy":
          result = await ragApi.refreshHierarchy();
          break;
        case "indexCorpus":
          result = await ragApi.indexCorpus(pending.corpus);
          break;
        case "raptor":
          result = await ragApi.raptor(pending.corpus);
          break;
      }
      setActiveTaskId(result.task_id);
      toast.success(`Queued ${describe(pending)}`, { description: `task_id=${result.task_id}` });
      corpora.refetch();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Action failed: ${msg}`);
    } finally {
      setPending(null);
    }
  };

  return (
    <PageContainer
      title="RAG Admin"
      subtitle="Refresh L0 base + hierarchy. Per-corpus reindex / RAPTOR. Each action queues a Celery task; tail progress on the right."
      extra={
        <div className="flex items-center gap-2">
          <Button variant="warn" size="sm" onClick={() => setPending({ kind: "refreshL0" })} className="gap-2">
            <RefreshCcw className="h-4 w-4" /> Refresh L0
          </Button>
          <Button variant="warn" size="sm" onClick={() => setPending({ kind: "refreshHierarchy" })} className="gap-2">
            <GitBranch className="h-4 w-4" /> Refresh hierarchy
          </Button>
        </div>
      }
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_360px]">
        <Card className="h-[calc(100vh-200px)]">
          <CardContent className="h-full p-0">
            <DataTable<RagCorpusInfo>
              rows={corpora.data ?? []}
              rowKey={(c) => c.name}
              emptyState={
                corpora.isPending ? (
                  <span>Loading corpora…</span>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <Network className="h-6 w-6" />
                    <span>No corpora registered.</span>
                  </div>
                )
              }
              columns={[
                {
                  key: "name",
                  header: "Corpus",
                  render: (c) => (
                    <div className="flex flex-col">
                      <span className="font-mono">{c.name}</span>
                      {c.description ? (
                        <span className="line-clamp-1 text-[10px] text-[var(--text-muted)]">{c.description}</span>
                      ) : null}
                    </div>
                  ),
                },
                {
                  key: "order",
                  header: "Order",
                  width: 90,
                  render: (c) => <Badge variant="secondary">{c.order}</Badge>,
                },
                {
                  key: "l1",
                  header: "L1 / L2",
                  width: 200,
                  render: (c) => (
                    <span className="font-mono text-xs">
                      {c.l1} / {c.l2}
                    </span>
                  ),
                },
                {
                  key: "iceberg",
                  header: "Iceberg",
                  render: (c) => (
                    <span className="font-mono text-[10px] text-[var(--text-secondary)]">
                      {c.iceberg ?? "—"}
                    </span>
                  ),
                },
                {
                  key: "chunks",
                  header: "Chunks",
                  width: 100,
                  align: "right",
                  render: (c) => <Numeric value={c.chunks ?? null} kind="integer" digits={0} color="neutral" />,
                },
                {
                  key: "last_indexed_at",
                  header: "Indexed",
                  width: 130,
                  align: "right",
                  render: (c) => (
                    <span className="text-[var(--text-secondary)]">
                      {c.last_indexed_at ? formatTime(c.last_indexed_at) : "—"}
                    </span>
                  ),
                },
                {
                  key: "actions",
                  header: "Actions",
                  width: 200,
                  render: (c) => (
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setPending({ kind: "indexCorpus", corpus: c.name });
                        }}
                      >
                        Reindex
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setPending({ kind: "raptor", corpus: c.name });
                        }}
                        className="gap-1"
                      >
                        <Sparkles className="h-3 w-3" /> RAPTOR
                      </Button>
                    </div>
                  ),
                },
              ]}
            />
          </CardContent>
        </Card>

        <Card className="h-[calc(100vh-200px)]">
          <CardHeader>
            <CardTitle>Active task</CardTitle>
            <Badge variant={stream.status === "open" ? "positive" : "secondary"}>{stream.status}</Badge>
          </CardHeader>
          <CardContent className="h-full p-3">
            {!activeTaskId ? (
              <p className="text-xs text-[var(--text-secondary)]">
                Trigger an action to tail progress here.
              </p>
            ) : (
              <>
                <div className="mb-2 text-[10px] text-[var(--text-muted)]">{activeTaskId}</div>
                <ProgressTimeline events={stream.events} height={"calc(100% - 32px)"} follow />
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {pending ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(open) => !open && setPending(null)}
          title={describe(pending)}
          consequence={consequenceFor(pending)}
          details={detailsFor(pending)}
          confirmPhrase={
            pending.kind === "refreshL0" || pending.kind === "refreshHierarchy" ? "REFRESH" : ""
          }
          confirmLabel={describe(pending)}
          confirmVariant="warn"
          onConfirm={submit}
        />
      ) : null}
    </PageContainer>
  );
}

function describe(action: ActionKind): string {
  switch (action.kind) {
    case "refreshL0":
      return "Refresh L0 base";
    case "refreshHierarchy":
      return "Refresh hierarchy";
    case "indexCorpus":
      return `Reindex ${action.corpus}`;
    case "raptor":
      return `RAPTOR ${action.corpus}`;
  }
}

function consequenceFor(action: ActionKind): string {
  switch (action.kind) {
    case "refreshL0":
      return "Rebuilds the L0 alpha base across all corpora. Existing embeddings remain readable; the new index swaps in atomically once writes complete.";
    case "refreshHierarchy":
      return "Recomputes the L1 + L2 + L3 hierarchy from the L0 base. Long-running on large corpora; safe to leave running in the background.";
    case "indexCorpus":
      return "Re-indexes a single corpus' embeddings from scratch. Existing index stays available until the swap completes.";
    case "raptor":
      return "Runs RAPTOR clustering for the corpus. Adds higher-order summary chunks; does not delete existing chunks.";
  }
}

function detailsFor(action: ActionKind): Array<{ label: string; value: React.ReactNode; tone?: "warn" | "neutral" }> {
  switch (action.kind) {
    case "indexCorpus":
    case "raptor":
      return [{ label: "Corpus", value: action.corpus }];
    default:
      return [{ label: "Scope", value: action.kind === "refreshL0" ? "All corpora (L0)" : "All corpora (L1/L2/L3)", tone: "warn" }];
  }
}
