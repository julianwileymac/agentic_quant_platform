import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApiQuery } from "@/lib/api/hooks";
import type { AgentSpecSummary } from "@/lib/api/agents";

export function AgentTemplatesRoute() {
  const list = useApiQuery<AgentSpecSummary[]>({
    queryKey: ["agents", "specs"],
    path: "/agents/specs",
    select: (raw) => (Array.isArray(raw) ? (raw as AgentSpecSummary[]) : []),
  });
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    const specs = list.data ?? [];
    const q = filter.trim().toLowerCase();
    if (!q) return specs;
    return specs.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.role ?? "").toLowerCase().includes(q) ||
        (s.description ?? "").toLowerCase().includes(q),
    );
  }, [list.data, filter]);

  return (
    <PageContainer
      title="Agent Templates"
      subtitle={`Reusable agent personas. Click "Use this template" to launch the AgentBacktestWizard with the spec preselected.`}
    >
      <div className="mb-4 max-w-md">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
          <Input
            placeholder="Filter templates"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="pl-7"
          />
        </div>
      </div>

      {list.isPending ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading templates…</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm italic text-[var(--text-secondary)]">No templates available.</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((s) => (
            <Card key={s.name} className="flex flex-col">
              <CardHeader>
                <CardTitle className="font-mono text-base">{s.name}</CardTitle>
                <Badge variant="secondary">{s.role}</Badge>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col gap-2">
                <p className="line-clamp-3 text-sm text-[var(--text-secondary)]">
                  {s.description ?? "No description provided."}
                </p>
                {s.annotations && s.annotations.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {s.annotations.map((a) => (
                      <Badge key={a} variant="outline" className="text-[10px]">
                        {a}
                      </Badge>
                    ))}
                  </div>
                ) : null}
                <div className="mt-auto pt-2">
                  <Link to={`/backtest/new?agent=${encodeURIComponent(s.name)}`} className="block">
                    <Button variant="outline" size="sm" className="w-full">
                      Use this template
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </PageContainer>
  );
}
