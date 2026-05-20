import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useRegistryKind, type ComponentSummary } from "@/lib/api/registry";

interface Props {
  kind: string;
  title: string;
  subtitle: string;
}

/**
 * Generic /registry/{kind} browser. Drives the ML zoo, RL zoo, and RL
 * component library by varying `kind`. Each row is a registered class
 * with kwargs schema; click for spec via `/registry/{kind}/{alias}`.
 */
export function RegistryBrowser({ kind, title, subtitle }: Props) {
  const list = useRegistryKind(kind);
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [category, setCategory] = useState("");

  const sources = useMemo(() => {
    const s = new Set<string>();
    for (const r of list.data ?? []) {
      if (r.source) s.add(r.source);
    }
    return Array.from(s).sort();
  }, [list.data]);
  const categories = useMemo(() => {
    const c = new Set<string>();
    for (const r of list.data ?? []) {
      if (r.category) c.add(r.category);
    }
    return Array.from(c).sort();
  }, [list.data]);

  const filtered = useMemo(() => {
    const items = list.data ?? [];
    const lq = q.trim().toLowerCase();
    return items.filter((r) => {
      if (lq && !`${r.alias} ${r.qualname} ${r.doc ?? ""}`.toLowerCase().includes(lq))
        return false;
      if (source && r.source !== source) return false;
      if (category && r.category !== category) return false;
      return true;
    });
  }, [list.data, q, source, category]);

  const columns: ColumnDef<ComponentSummary>[] = [
    { key: "alias", header: "Alias", render: (r) => <span className="font-mono">{r.alias}</span> },
    {
      key: "qualname",
      header: "Class path",
      render: (r) => <span className="font-mono text-xs text-[var(--text-secondary)]">{r.qualname}</span>,
    },
    {
      key: "category",
      header: "Category",
      width: 130,
      render: (r) => <Badge variant="secondary">{r.category ?? "—"}</Badge>,
    },
    {
      key: "source",
      header: "Source",
      width: 120,
      render: (r) => <Badge variant="secondary">{r.source ?? "—"}</Badge>,
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
    {
      key: "params",
      header: "Params",
      width: 100,
      align: "right",
      render: (r) => <span className="font-mono">{r.params?.length ?? 0}</span>,
    },
  ];

  return (
    <PageContainer
      title={title}
      subtitle={subtitle}
      extra={
        <div className="flex items-center gap-2">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
          >
            <option value="">all sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
          >
            <option value="">all categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter aliases / classes / docs"
              className="w-72 pl-7"
            />
          </div>
          <Badge variant="secondary">{filtered.length}</Badge>
        </div>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<ComponentSummary>
            rows={filtered}
            rowKey={(r) => r.alias}
            columns={columns}
            emptyState={
              list.isPending ? <span>Loading…</span> : <span>No components in /{kind}.</span>
            }
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
