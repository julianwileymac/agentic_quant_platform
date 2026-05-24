import "highlight.js/styles/github-dark.css";

import { BookOpen, Search } from "lucide-react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

interface DocsTocEntry {
  slug: string;
  title: string;
  group?: string;
}

interface DocsIndex {
  entries: DocsTocEntry[];
}

interface DocsPage {
  slug: string;
  title: string;
  body: string;
}

export function DocsRoute() {
  const [filter, setFilter] = useState("");
  const [activeSlug, setActiveSlug] = useState<string | null>(null);

  const index = useApiQuery<DocsIndex | DocsTocEntry[]>({
    queryKey: ["docs", "index"],
    path: "/docs/index",
    retry: false,
  });

  const entries: DocsTocEntry[] = useMemo(() => {
    const raw = index.data;
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    return raw.entries ?? [];
  }, [index.data]);

  const stub = index.error instanceof ApiError && index.error.status === 404;

  const filtered = entries.filter((e) =>
    `${e.title} ${e.slug} ${e.group ?? ""}`.toLowerCase().includes(filter.toLowerCase()),
  );

  const groups = useMemo(() => {
    const m = new Map<string, DocsTocEntry[]>();
    filtered.forEach((e) => {
      const k = e.group ?? "Docs";
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(e);
    });
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  const page = useApiQuery<DocsPage>({
    queryKey: ["docs", "page", activeSlug],
    path: `/docs/${encodeURIComponent(activeSlug ?? "")}`,
    enabled: Boolean(activeSlug),
    retry: false,
  });

  return (
    <PageContainer
      title="Docs"
      subtitle="Markdown / MDX rendered from FastAPI's docs router. TOC search filters across titles, slugs, and groups."
    >
      {stub ? (
        <Card className="mb-3">
          <CardHeader>
            <CardTitle>Pending API: GET /docs/index</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--text-secondary)]">
              The docs index endpoint isn't registered on this build. Until then, refer to the
              legacy webui at <code className="font-mono">/docs</code>, or the markdown files under{" "}
              <code className="font-mono">aqp_docs/</code> on disk.
            </p>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[320px_1fr]">
        <Card className="h-[calc(100vh-220px)] overflow-hidden">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="h-4 w-4" /> Contents
            </CardTitle>
            <Badge variant="secondary">{entries.length}</Badge>
          </CardHeader>
          <CardContent className="grid h-full grid-rows-[auto_1fr] gap-2 p-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <Input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter docs…"
                className="pl-7"
              />
            </div>
            <nav className="flex h-full flex-col gap-3 overflow-auto pr-1">
              {groups.length === 0 ? (
                <p className="text-xs italic text-[var(--text-secondary)]">
                  {index.isPending ? "Loading…" : "No matches."}
                </p>
              ) : (
                groups.map(([group, items]) => (
                  <div key={group} className="flex flex-col gap-1">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
                      {group}
                    </div>
                    {items.map((e) => {
                      const active = e.slug === activeSlug;
                      return (
                        <Button
                          key={e.slug}
                          variant={active ? "default" : "ghost"}
                          size="sm"
                          className="justify-start text-left"
                          onClick={() => setActiveSlug(e.slug)}
                        >
                          <span className="truncate text-xs">{e.title}</span>
                        </Button>
                      );
                    })}
                  </div>
                ))
              )}
            </nav>
          </CardContent>
        </Card>

        <Card className="h-[calc(100vh-220px)]">
          <CardHeader>
            <CardTitle>{page.data?.title ?? activeSlug ?? "Pick a doc"}</CardTitle>
            {activeSlug ? (
              <code className="font-mono text-[10px] text-[var(--text-secondary)]">
                /docs/{activeSlug}
              </code>
            ) : null}
          </CardHeader>
          <CardContent className="h-full overflow-auto p-4">
            {!activeSlug ? (
              <p className="text-sm italic text-[var(--text-secondary)]">
                Select a doc from the contents pane.
              </p>
            ) : page.isPending ? (
              <p className="text-sm text-[var(--text-secondary)]">Loading {activeSlug}…</p>
            ) : page.error ? (
              <p className="text-sm text-[var(--neg-fg)]">
                Failed to load: {(page.error as Error).message}
              </p>
            ) : page.data ? (
              <article className={cn("prose prose-invert max-w-none text-sm")}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                  {page.data.body}
                </ReactMarkdown>
              </article>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
