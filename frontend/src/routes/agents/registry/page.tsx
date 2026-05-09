import { Search, Telescope } from "lucide-react";
import { useMemo, useState } from "react";

import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useApiQuery } from "@/lib/api/hooks";
import type { AgentSpecDetail, AgentSpecSummary } from "@/lib/api/agents";
import { formatTime } from "@/lib/utils";

type RoleBucket = "research" | "selection" | "trader" | "analysis" | "other";

function bucketFor(name: string, role: string | undefined): RoleBucket {
  const explicit = (role ?? "").toLowerCase();
  if (
    explicit === "research" ||
    explicit === "selection" ||
    explicit === "trader" ||
    explicit === "analysis"
  ) {
    return explicit;
  }
  if (name.startsWith("research.")) return "research";
  if (name.startsWith("selection.")) return "selection";
  if (name.startsWith("trader.")) return "trader";
  if (name.startsWith("analysis.")) return "analysis";
  return "other";
}

const BUCKET_TONE: Record<RoleBucket, "positive" | "default" | "warn" | "secondary" | "negative"> = {
  research: "positive",
  selection: "default",
  trader: "warn",
  analysis: "secondary",
  other: "secondary",
};

export function AgentRegistryRoute() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const specs = useApiQuery<AgentSpecSummary[]>({
    queryKey: ["agents", "specs"],
    path: "/agents/specs",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const detail = useApiQuery<AgentSpecDetail>({
    queryKey: ["agents", "spec", selected],
    path: selected ? `/agents/specs/${encodeURIComponent(selected)}` : "/agents/specs",
    enabled: Boolean(selected),
  });

  const filtered = useMemo(() => {
    const list = specs.data ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((s) =>
      [s.name, s.role, s.description, ...(s.annotations ?? [])]
        .filter((x): x is string => Boolean(x))
        .some((x) => x.toLowerCase().includes(q)),
    );
  }, [specs.data, query]);

  return (
    <PageContainer
      title="Agent Registry"
      subtitle="Hash-locked spec snapshots persisted to agent_spec_versions. Click a row to inspect the full immutable spec."
      extra={
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by name / role / annotation"
            className="w-72 pl-8"
          />
        </div>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<AgentSpecSummary>
            rows={filtered}
            rowKey={(s) => s.name}
            onRowClick={(s) => setSelected(s.name)}
            emptyState={
              specs.isPending ? (
                <span>Loading specs…</span>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Telescope className="h-6 w-6" />
                  <span>No specs match the filter.</span>
                </div>
              )
            }
            columns={[
              {
                key: "name",
                header: "Spec",
                render: (s) => (
                  <div className="flex flex-col">
                    <span className="font-medium">{s.name}</span>
                    {s.description ? (
                      <span className="line-clamp-1 text-[10px] text-[var(--text-muted)]">{s.description}</span>
                    ) : null}
                  </div>
                ),
              },
              {
                key: "bucket",
                header: "Role",
                width: 120,
                render: (s) => {
                  const bucket = bucketFor(s.name, s.role);
                  return <Badge variant={BUCKET_TONE[bucket]}>{bucket}</Badge>;
                },
              },
              {
                key: "hash",
                header: "Latest hash",
                width: 160,
                render: (s) => (
                  <span className="font-mono text-xs">
                    {s.snapshot_hash ? s.snapshot_hash.slice(0, 12) : "—"}
                  </span>
                ),
              },
              {
                key: "n_tools",
                header: "Tools",
                width: 80,
                align: "right",
                render: (s) => <Numeric value={s.n_tools ?? null} kind="integer" digits={0} color="neutral" />,
              },
              {
                key: "n_rag",
                header: "RAG",
                width: 80,
                align: "right",
                render: (s) => <Numeric value={s.n_rag_clauses ?? null} kind="integer" digits={0} color="neutral" />,
              },
              {
                key: "memory",
                header: "Memory",
                width: 110,
                render: (s) => (
                  <span className="font-mono text-xs">{s.memory_kind ?? "—"}</span>
                ),
              },
              {
                key: "updated_at",
                header: "Updated",
                width: 140,
                align: "right",
                render: (s) => (
                  <span className="text-[var(--text-secondary)]">
                    {s.updated_at ? formatTime(s.updated_at) : "—"}
                  </span>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>

      <Dialog open={selected != null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="font-mono">{selected ?? "spec"}</DialogTitle>
            <DialogDescription>
              Hash-locked AgentSpec snapshot — immutable. Re-snapshotting via{" "}
              <code className="rounded bg-[var(--bg-app)] px-1 font-mono text-xs">
                aqp.agents.registry.persist_spec
              </code>{" "}
              creates a new version row.
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh] rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3">
            <pre className="whitespace-pre-wrap break-words font-mono text-xs">
              {detail.isPending
                ? "Loading…"
                : detail.error
                  ? `Failed: ${detail.error.message}`
                  : JSON.stringify(detail.data?.payload ?? detail.data ?? {}, null, 2)}
            </pre>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
