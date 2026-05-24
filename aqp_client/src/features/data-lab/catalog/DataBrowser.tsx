import { Database, FileCode2, Search, Tag } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  type LabCatalogEntry,
  listCatalogDatasets,
  listCatalogSnippets,
} from "@/lib/api/lab";

/** Custom MIME type the DataBrowser uses for richer drag payloads. */
export const LAB_DRAG_MIME = "application/x-aqp-lab-catalog-entry";

/**
 * Render the deterministic code snippet a catalog entry inserts when
 * the user drags it into an EDA cell. Mirrors the helpers preloaded
 * into :class:`aqp.lab.eda.kernel.EdaKernel`:
 *
 *   - ``db.scan('ns.tbl')`` — DuckDB-over-Iceberg for catalog datasets
 *   - ``iceberg.read_arrow('ns.tbl')`` — Arrow handle if the user
 *     wants the table directly
 *   - ``qdb.query('SELECT * FROM tbl LIMIT 1000')`` — QuestDB
 *     (heuristic: kind === 'questdb' OR namespace starts with 'qdb_')
 *   - snippets surface a one-line ``# snippet:<name>`` comment because
 *     dragging a snippet into a cell is a Phase 2 expansion (the
 *     user will be able to insert the snippet as a function call).
 */
export function buildInsertionSnippet(entry: LabCatalogEntry): string {
  const namespace = (entry.namespace ?? "").trim();
  const isQuestDb =
    entry.kind === "questdb" || (namespace && namespace.toLowerCase().startsWith("qdb_"));
  const isIceberg =
    entry.kind === "iceberg" ||
    (namespace && namespace.toLowerCase().startsWith("aqp_"));
  const isSnippet = entry.kind === "snippet";

  if (isSnippet) {
    return `# snippet:${entry.name} (id=${entry.id})\n`;
  }
  if (isQuestDb) {
    const tableName = entry.name.split(".").pop() ?? entry.name;
    return `qdb.query("SELECT * FROM ${tableName} LIMIT 1000")\n`;
  }
  if (isIceberg && namespace) {
    return `db.scan("${namespace}.${entry.name}")\n`;
  }
  // Generic catalog entry — fall back to db.scan with the namespace+name
  // if we have it, otherwise just the bare name for the user to edit.
  if (namespace) {
    return `db.scan("${namespace}.${entry.name}")\n`;
  }
  return `db.scan("${entry.name}")\n`;
}

interface DataBrowserProps {
  workspaceId?: string;
  /** Called when the user clicks "Insert" on a catalog entry. The
   *  parent (EDA cell stack, Testing canvas) is responsible for
   *  acting on the insertion (e.g. dropping a scan() into a cell). */
  onInsert?: (entry: LabCatalogEntry) => void;
}

type Tab = "datasets" | "snippets";

/**
 * Left-rail catalog browser. Phase 1 ships dataset + snippet
 * tabs sourced from the new ``/lab/catalog/*`` endpoints. The
 * pgvector semantic search lands in Phase 2 once we have an
 * embedding pipeline for the dataset metadata; for now we offer a
 * client-side substring filter so the UI flow is exercised.
 */
export function DataBrowser({ workspaceId, onInsert }: DataBrowserProps) {
  const [tab, setTab] = useState<Tab>("datasets");
  const [q, setQ] = useState("");
  const [datasets, setDatasets] = useState<LabCatalogEntry[]>([]);
  const [snippets, setSnippets] = useState<LabCatalogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      listCatalogDatasets({ limit: 200 }).catch(() => [] as LabCatalogEntry[]),
      listCatalogSnippets(workspaceId).catch(() => [] as LabCatalogEntry[]),
    ])
      .then(([ds, sn]) => {
        if (!cancelled) {
          setDatasets(ds);
          setSnippets(sn);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const filtered = useMemo(() => {
    const source = tab === "datasets" ? datasets : snippets;
    const needle = q.trim().toLowerCase();
    if (!needle) return source;
    return source.filter(
      (e) =>
        e.name.toLowerCase().includes(needle) ||
        (e.description ?? "").toLowerCase().includes(needle) ||
        e.tags.some((t) => t.toLowerCase().includes(needle)),
    );
  }, [tab, datasets, snippets, q]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center gap-1">
        <Button
          variant={tab === "datasets" ? "default" : "ghost"}
          size="sm"
          className="gap-2"
          onClick={() => setTab("datasets")}
        >
          <Database className="h-4 w-4" /> Datasets
        </Button>
        <Button
          variant={tab === "snippets" ? "default" : "ghost"}
          size="sm"
          className="gap-2"
          onClick={() => setTab("snippets")}
        >
          <FileCode2 className="h-4 w-4" /> Snippets
        </Button>
      </div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder={`Filter ${tab}…`}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="pl-8"
        />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {loading ? (
          <div className="p-2 text-xs text-muted-foreground">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="p-2 text-xs text-muted-foreground">
            No {tab} match{q ? ` "${q}"` : ""}.
          </div>
        ) : (
          filtered.map((entry) => {
            const insertion = buildInsertionSnippet(entry);
            return (
              <Card
                key={entry.id}
                className="cursor-grab border-l-2 active:cursor-grabbing"
                draggable
                onDragStart={(e) => {
                  // Two payloads: plain text for the CodeMirror /
                  // textarea fallback path, plus a rich JSON payload
                  // on a custom MIME type so future drop targets
                  // (Testing canvas) can decode the full entry.
                  e.dataTransfer.setData("text/plain", insertion);
                  e.dataTransfer.setData(
                    LAB_DRAG_MIME,
                    JSON.stringify({
                      entry,
                      insertion,
                      origin: "data-browser",
                    }),
                  );
                  e.dataTransfer.effectAllowed = "copy";
                }}
              >
                <CardContent className="space-y-1 py-2">
                  <div className="flex items-center gap-2 text-xs">
                    <code className="truncate font-mono">{entry.name}</code>
                    {entry.medallion_layer ? (
                      <Badge variant="outline" className="ml-auto">
                        {entry.medallion_layer}
                      </Badge>
                    ) : null}
                  </div>
                  {entry.description ? (
                    <div className="line-clamp-2 text-[11px] text-muted-foreground">
                      {entry.description}
                    </div>
                  ) : null}
                  {entry.tags.length ? (
                    <div className="flex flex-wrap gap-1">
                      {entry.tags.slice(0, 4).map((t) => (
                        <Badge key={t} variant="secondary" className="gap-1">
                          <Tag className="h-3 w-3" />
                          {t}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                  <div className="flex items-center gap-2 pt-1">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 px-2 text-[11px]"
                      onClick={() => onInsert?.(entry)}
                      title="Insert at the active cell — same payload as drag-drop."
                    >
                      Insert
                    </Button>
                    <span
                      className="ml-auto truncate text-[10px] text-muted-foreground"
                      title={insertion}
                    >
                      drag &rarr; cell
                    </span>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}

export default DataBrowser;
