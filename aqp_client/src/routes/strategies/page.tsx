import { AppWindow, Plus, RefreshCcw, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApiQuery } from "@/lib/api/hooks";
import { type StrategySummary } from "@/lib/api/strategies";
import { formatTime } from "@/lib/utils";

export function StrategiesRoute() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const list = useApiQuery<StrategySummary[]>({
    queryKey: ["strategies"],
    path: "/strategies",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const filtered = useMemo(() => {
    const items = list.data ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((s) =>
      [s.name, s.class, s.module_path, s.description, ...(s.tags ?? [])]
        .filter((v): v is string => Boolean(v))
        .some((v) => v.toLowerCase().includes(q)),
    );
  }, [list.data, query]);

  return (
    <PageContainer
      title="Strategies"
      subtitle="Registered strategy catalog. Each row is a `class` / `module_path` / `kwargs` factory entry."
      extra={
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by name / class / tag"
              className="w-72 pl-8"
            />
          </div>
          <Button variant="ghost" size="sm" onClick={() => list.refetch()}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button asChild>
            <Link to="/workflows/strategy">
              <Plus className="h-4 w-4" /> New strategy
            </Link>
          </Button>
        </div>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<StrategySummary>
            rows={filtered}
            rowKey={(s) => s.id}
            onRowClick={(s) => navigate(`/strategies/${s.id}`)}
            emptyState={
              list.isPending ? (
                <span>Loading strategies…</span>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <AppWindow className="h-6 w-6" />
                  <span>No strategies registered.</span>
                </div>
              )
            }
            columns={[
              {
                key: "name",
                header: "Strategy",
                render: (s) => (
                  <div className="flex flex-col">
                    <span className="font-medium">{s.name}</span>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">{s.id}</span>
                  </div>
                ),
              },
              {
                key: "class",
                header: "Class",
                width: 220,
                render: (s) => <span className="font-mono text-xs">{s.class ?? "—"}</span>,
              },
              {
                key: "module_path",
                header: "Module",
                render: (s) => (
                  <span className="font-mono text-[10px] text-[var(--text-secondary)]">
                    {s.module_path ?? "—"}
                  </span>
                ),
              },
              {
                key: "tags",
                header: "Tags",
                width: 160,
                render: (s) => (
                  <div className="flex flex-wrap gap-1">
                    {(s.tags ?? []).slice(0, 3).map((t) => (
                      <Badge key={t} variant="outline" className="text-[10px]">
                        {t}
                      </Badge>
                    ))}
                  </div>
                ),
              },
              {
                key: "sharpe",
                header: "Sharpe (30d)",
                width: 110,
                align: "right",
                render: (s) => <Numeric value={s.last_sharpe ?? null} kind="decimal" digits={2} color="auto" />,
              },
              {
                key: "max_dd",
                header: "Max DD",
                width: 100,
                align: "right",
                render: (s) => (
                  <Numeric
                    value={s.last_max_drawdown ?? null}
                    kind="percent"
                    digits={2}
                    color="force-neg"
                  />
                ),
              },
              {
                key: "last_run_at",
                header: "Last run",
                width: 130,
                align: "right",
                render: (s) => (
                  <span className="text-[var(--text-secondary)]">
                    {s.last_run_at ? formatTime(s.last_run_at) : "—"}
                  </span>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
