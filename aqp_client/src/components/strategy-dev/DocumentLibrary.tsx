import { BookOpen, Filter, Search, Upload as UploadIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useApiQuery } from "@/lib/api/hooks";

import { PaperDetail } from "./PaperDetail";
import { PaperUpload } from "./PaperUpload";

interface PaperListItem {
  id: string;
  title: string;
  authors?: string[];
  author_institution?: string | null;
  publication_year?: number | null;
  asset_class?: string[];
  strategy_family?: string | null;
  contains_mathematics?: boolean;
  equation_count?: number;
  chunk_count?: number;
  parser_used?: string | null;
  created_at?: string;
}

interface PaperListResp {
  items?: PaperListItem[];
}

/**
 * Top-level document library: list + filter + upload + detail view.
 * Wraps the new `/rag/papers` REST routes added in this same diff.
 */
export function DocumentLibrary() {
  const [search, setSearch] = useState("");
  const [familyFilter, setFamilyFilter] = useState<string>("");
  const [showUpload, setShowUpload] = useState(false);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);

  const papers = useApiQuery<PaperListItem[]>({
    queryKey: ["rag", "papers", { search, familyFilter }],
    path: "/rag/papers",
    query: {
      ...(search ? { q: search } : {}),
      ...(familyFilter ? { strategy_family: familyFilter } : {}),
      limit: 200,
    },
    select: (raw) => {
      if (Array.isArray(raw)) return raw as PaperListItem[];
      const obj = raw as PaperListResp | undefined;
      return Array.isArray(obj?.items) ? obj!.items! : [];
    },
    staleTime: 30_000,
  });

  const filtered = papers.data ?? [];

  const families = useMemo(() => {
    const set = new Set<string>();
    for (const p of papers.data ?? []) {
      if (p.strategy_family) set.add(p.strategy_family);
    }
    return Array.from(set).sort();
  }, [papers.data]);

  if (selectedPaperId) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-3">
        <Button variant="ghost" size="sm" onClick={() => setSelectedPaperId(null)}>
          ← Back to library
        </Button>
        <div className="min-h-0 flex-1 overflow-auto">
          <PaperDetail paperId={selectedPaperId} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title / abstract / equations…"
              className="w-72 pl-8"
            />
          </div>
          <div className="flex items-center gap-1">
            <Filter className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
            <select
              value={familyFilter}
              onChange={(e) => setFamilyFilter(e.target.value)}
              className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-2 text-xs"
            >
              <option value="">All families</option>
              {families.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
        </div>
        <Button onClick={() => setShowUpload((v) => !v)}>
          <UploadIcon className="h-4 w-4" />
          {showUpload ? "Hide uploader" : "Upload paper"}
        </Button>
      </div>

      {showUpload ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <div className="flex items-center gap-2">
                <UploadIcon className="h-4 w-4" />
                Upload research paper
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <PaperUpload
              onUploaded={(paperId) => {
                setShowUpload(false);
                void papers.refetch();
                setSelectedPaperId(paperId);
              }}
            />
          </CardContent>
        </Card>
      ) : null}

      <Card className="flex min-h-0 flex-1 flex-col">
        <CardHeader>
          <CardTitle>
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4" />
              Library
              <Badge variant="outline" className="text-[10px]">
                {filtered.length}
              </Badge>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col p-0">
          <ScrollArea className="flex-1">
            <ul className="divide-y divide-[var(--border-subtle)]">
              {filtered.length === 0 ? (
                <li className="py-8 text-center text-xs text-[var(--text-secondary)]">
                  {papers.isLoading ? "Loading papers…" : "No papers yet — upload one above."}
                </li>
              ) : null}
              {filtered.map((p) => (
                <li
                  key={p.id}
                  className="cursor-pointer px-4 py-2 hover:bg-[var(--bg-elevated)]"
                  onClick={() => setSelectedPaperId(p.id)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate font-medium text-sm">{p.title || p.id}</span>
                      <span className="truncate text-[11px] text-[var(--text-secondary)]">
                        {p.authors?.join(", ") || "—"}
                        {p.author_institution ? ` · ${p.author_institution}` : ""}
                        {p.publication_year ? ` · ${p.publication_year}` : ""}
                      </span>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-1">
                      {p.contains_mathematics ? (
                        <Badge variant="default" className="text-[10px]">
                          {p.equation_count ?? 0} eq.
                        </Badge>
                      ) : null}
                      {p.strategy_family ? (
                        <Badge variant="secondary" className="text-[10px]">
                          {p.strategy_family}
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                  {p.asset_class?.length ? (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {p.asset_class.map((ac) => (
                        <Badge key={ac} variant="outline" className="text-[9px]">
                          {ac}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
