import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApiQuery } from "@/lib/api/hooks";

interface LearnTopic {
  id: string;
  title: string;
  category: string;
  level: string;
  summary: string;
  related?: string[];
}

interface LearnSource {
  id: string;
  name: string;
  url: string;
  category: string;
  description?: string;
  tags?: string[];
}

export function TaxonomyExplorer() {
  const [params, setParams] = useSearchParams();
  const initialTab = params.get("tab") === "sources" ? "sources" : "topics";
  const [tab, setTab] = useState(initialTab);
  const [q, setQ] = useState("");

  const topics = useApiQuery<LearnTopic[]>({
    queryKey: ["learn", "topics"],
    path: "/learn/topics",
    select: (raw) => (Array.isArray(raw) ? (raw as LearnTopic[]) : []),
  });
  const sources = useApiQuery<LearnSource[]>({
    queryKey: ["learn", "sources"],
    path: "/learn/sources",
    select: (raw) => (Array.isArray(raw) ? (raw as LearnSource[]) : []),
  });

  const filteredTopics = useMemo(() => {
    const items = topics.data ?? [];
    const lq = q.trim().toLowerCase();
    if (!lq) return items;
    return items.filter(
      (t) =>
        t.title.toLowerCase().includes(lq) ||
        t.summary.toLowerCase().includes(lq) ||
        t.category.toLowerCase().includes(lq),
    );
  }, [topics.data, q]);
  const filteredSources = useMemo(() => {
    const items = sources.data ?? [];
    const lq = q.trim().toLowerCase();
    if (!lq) return items;
    return items.filter(
      (s) =>
        s.name.toLowerCase().includes(lq) ||
        (s.description ?? "").toLowerCase().includes(lq) ||
        s.category.toLowerCase().includes(lq),
    );
  }, [sources.data, q]);

  const onTabChange = (next: string) => {
    setTab(next);
    if (next === "sources") setParams({ tab: "sources" });
    else setParams({});
  };

  const topicColumns: ColumnDef<LearnTopic>[] = [
    { key: "title", header: "Topic", render: (r) => <span className="font-medium">{r.title}</span> },
    { key: "category", header: "Category", width: 140, render: (r) => <Badge variant="secondary">{r.category}</Badge> },
    { key: "level", header: "Level", width: 110, render: (r) => <Badge variant="outline">{r.level}</Badge> },
    { key: "summary", header: "Summary", render: (r) => <span className="text-xs">{r.summary}</span> },
  ];
  const sourceColumns: ColumnDef<LearnSource>[] = [
    { key: "name", header: "Source", render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "category", header: "Category", width: 140, render: (r) => <Badge variant="secondary">{r.category}</Badge> },
    {
      key: "url",
      header: "URL",
      render: (r) => (
        <a href={r.url} target="_blank" rel="noreferrer" className="font-mono text-xs text-[var(--info-fg)] underline">
          {r.url}
        </a>
      ),
    },
    {
      key: "tags",
      header: "Tags",
      render: (r) => (
        <div className="flex flex-wrap gap-1">
          {(r.tags ?? []).map((t) => (
            <Badge key={t} variant="outline" className="text-[10px]">
              {t}
            </Badge>
          ))}
        </div>
      ),
    },
  ];

  return (
    <PageContainer
      title="Learn / Taxonomy"
      subtitle="Curated topic + source library that grounds the agentic platform's vocabulary. Filter by free-text search; hop between topics and external sources via the tab strip."
      extra={
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter topics / sources"
            className="w-72 pl-7"
          />
        </div>
      }
    >
      <Tabs value={tab} onValueChange={onTabChange}>
        <TabsList>
          <TabsTrigger value="topics">Topics</TabsTrigger>
          <TabsTrigger value="sources">Source libraries</TabsTrigger>
        </TabsList>

        <TabsContent value="topics" className="mt-3">
          <Card className="h-[calc(100vh-260px)]">
            <CardContent className="h-full p-0">
              <DataTable<LearnTopic>
                rows={filteredTopics}
                rowKey={(r) => r.id}
                columns={topicColumns}
                emptyState={topics.isPending ? <span>Loading…</span> : <span>No topics.</span>}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sources" className="mt-3">
          <Card className="h-[calc(100vh-260px)]">
            <CardContent className="h-full p-0">
              <DataTable<LearnSource>
                rows={filteredSources}
                rowKey={(r) => r.id}
                columns={sourceColumns}
                emptyState={sources.isPending ? <span>Loading…</span> : <span>No sources.</span>}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}
