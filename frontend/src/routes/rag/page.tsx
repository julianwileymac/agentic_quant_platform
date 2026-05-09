import { Network, Search } from "lucide-react";
import { useState } from "react";

import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { ragApi, type RagHit } from "@/lib/api/rag";

type Mode = "query" | "walk";

export function RagExplorerRoute() {
  const [mode, setMode] = useState<Mode>("query");
  const [query, setQuery] = useState("");
  const [corpus, setCorpus] = useState("");
  const [level, setLevel] = useState("");
  const [vtSymbol, setVtSymbol] = useState("");
  const [k, setK] = useState(10);
  const [hits, setHits] = useState<RagHit[]>([]);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!query.trim()) return;
    setBusy(true);
    try {
      const res =
        mode === "query"
          ? await ragApi.query({
              query,
              ...(corpus ? { corpus } : {}),
              ...(level ? { level } : {}),
              ...(vtSymbol ? { vt_symbol: vtSymbol } : {}),
              k,
            })
          : await ragApi.walk({
              query,
              ...(vtSymbol ? { vt_symbol: vtSymbol } : {}),
              per_level_k: 5,
              final_k: k,
            });
      setHits(res);
      toast.success(`${res.length} hits returned`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Query failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  };

  const grouped = mode === "walk" ? groupByLevel(hits) : null;

  return (
    <PageContainer
      title="RAG Explorer"
      subtitle="HierarchicalRAG query + walk. All retrievals route through HierarchicalRAG (AGENTS.md rule 11) so embeddings stay consistent with agent reads."
    >
      <Card className="mb-3">
        <CardContent className="py-3">
          <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)}>
            <TabsList>
              <TabsTrigger value="query">Query</TabsTrigger>
              <TabsTrigger value="walk">Walk (hierarchy)</TabsTrigger>
            </TabsList>
            <TabsContent value="query">
              <p className="text-xs text-[var(--text-secondary)]">
                Direct semantic search against a single level / corpus. Results are returned ranked
                by score.
              </p>
            </TabsContent>
            <TabsContent value="walk">
              <p className="text-xs text-[var(--text-secondary)]">
                Hierarchical walk across L1 / L2 / L3 layers, aggregating per-level top-k hits.
              </p>
            </TabsContent>
          </Tabs>

          <form
            className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto] lg:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <div className="grid gap-3 lg:grid-cols-4">
              <div className="flex flex-col gap-1 lg:col-span-2">
                <Label htmlFor="rag-q">Query</Label>
                <Input
                  id="rag-q"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="What's a robust mean-reversion alpha for AAPL intraday?"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="rag-vt">vt_symbol</Label>
                <Input
                  id="rag-vt"
                  value={vtSymbol}
                  onChange={(e) => setVtSymbol(e.target.value)}
                  placeholder="optional"
                  className="font-mono"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="rag-k">k</Label>
                <Input
                  id="rag-k"
                  type="number"
                  min={1}
                  max={50}
                  value={k}
                  onChange={(e) => setK(Number(e.target.value) || 10)}
                />
              </div>
              {mode === "query" ? (
                <>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="rag-corpus">corpus</Label>
                    <Input
                      id="rag-corpus"
                      value={corpus}
                      onChange={(e) => setCorpus(e.target.value)}
                      placeholder="optional"
                      className="font-mono"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="rag-level">level</Label>
                    <Input
                      id="rag-level"
                      value={level}
                      onChange={(e) => setLevel(e.target.value)}
                      placeholder="optional"
                      className="font-mono"
                    />
                  </div>
                </>
              ) : null}
            </div>
            <Button type="submit" disabled={!query.trim() || busy} className="gap-2 self-end">
              <Search className="h-4 w-4" /> {busy ? "Searching…" : mode === "query" ? "Query" : "Walk"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="h-[calc(100vh-360px)]">
        <CardHeader>
          <CardTitle>Hits</CardTitle>
          <Badge variant="secondary">{hits.length}</Badge>
        </CardHeader>
        <CardContent className="h-full p-0">
          <ScrollArea className="h-full">
            {hits.length === 0 ? (
              <div className="flex h-32 flex-col items-center justify-center gap-2 text-sm text-[var(--text-secondary)]">
                <Network className="h-6 w-6" />
                <span>{busy ? "Searching…" : "Run a query to see results."}</span>
              </div>
            ) : grouped ? (
              <div className="flex flex-col gap-3 p-3">
                {Object.entries(grouped).map(([lvl, items]) => (
                  <div key={lvl}>
                    <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
                      {lvl} ({items.length})
                    </div>
                    <ul className="flex flex-col gap-2">
                      {items.map((h) => (
                        <li key={h.doc_id}>
                          <HitCard hit={h} />
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ) : (
              <ul className="flex flex-col gap-2 p-3">
                {hits.map((h) => (
                  <li key={h.doc_id}>
                    <HitCard hit={h} />
                  </li>
                ))}
              </ul>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </PageContainer>
  );
}

function HitCard({ hit }: { hit: RagHit }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 py-2">
        <div className="flex items-center gap-2 text-xs">
          <Badge variant="default">{hit.corpus}</Badge>
          {hit.level ? <Badge variant="secondary">{hit.level}</Badge> : null}
          {hit.order ? <Badge variant="secondary">{hit.order}</Badge> : null}
          {hit.vt_symbol ? <Badge variant="outline">{hit.vt_symbol}</Badge> : null}
          <span className="ml-auto font-mono text-[10px]">
            <Numeric value={hit.score} kind="decimal" digits={3} color="auto" />
          </span>
        </div>
        <p className="text-sm text-[var(--text-primary)]">
          {hit.text.length > 480 ? `${hit.text.slice(0, 480)}…` : hit.text}
        </p>
        <div className="text-[10px] text-[var(--text-muted)]">
          doc {hit.doc_id} · chunk {hit.chunk_idx ?? "?"}
        </div>
      </CardContent>
    </Card>
  );
}

function groupByLevel(hits: RagHit[]): Record<string, RagHit[]> {
  const out: Record<string, RagHit[]> = {};
  for (const h of hits) {
    const key = h.level ?? "L?";
    if (!out[key]) out[key] = [];
    out[key]!.push(h);
  }
  return out;
}
