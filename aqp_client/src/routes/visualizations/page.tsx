import { BarChart3, Plus, RefreshCcw } from "lucide-react";
import { Link } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import type { SavedChart } from "@/lib/api/viz";
import { formatTime } from "@/lib/utils";

export function VisualizationsRoute() {
  const list = useApiQuery<SavedChart[]>({
    queryKey: ["visualizations"],
    path: "/visualizations",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  return (
    <PageContainer
      title="Visualizations"
      subtitle="Saved chart gallery. Each tile is a Recharts / lightweight-charts / D3 spec persisted with its dataset reference."
      extra={
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => list.refetch()}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button asChild>
            <Link to="/visualizations/new">
              <Plus className="h-4 w-4" /> New chart
            </Link>
          </Button>
        </div>
      }
    >
      {list.isPending ? (
        <p className="text-sm text-[var(--text-secondary)]">Loading…</p>
      ) : (list.data ?? []).length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center text-sm text-[var(--text-secondary)]">
            <BarChart3 className="h-8 w-8" />
            <span>No visualizations saved yet.</span>
            <span className="font-mono text-[10px]">GET /visualizations</span>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(list.data ?? []).map((c) => (
            <Card key={c.id} className="transition-colors hover:border-[var(--info-fg)]">
              <CardHeader>
                <CardTitle>{c.name}</CardTitle>
                <Badge variant="secondary">{c.viz_kind}</Badge>
              </CardHeader>
              <CardContent>
                {c.thumbnail_url ? (
                  <img
                    src={c.thumbnail_url}
                    alt={c.name}
                    className="mb-2 h-32 w-full rounded-md object-cover"
                  />
                ) : (
                  <div className="mb-2 flex h-32 items-center justify-center rounded-md border border-dashed border-[var(--border-default)] text-[10px] text-[var(--text-secondary)]">
                    Preview rendering — Phase 4 follow-up
                  </div>
                )}
                <p className="text-xs text-[var(--text-secondary)]">
                  {c.description ?? "No description."}
                </p>
                <div className="mt-2 flex items-center justify-between text-[10px] text-[var(--text-muted)]">
                  <span>{c.owner ?? "unknown owner"}</span>
                  <span>{c.updated_at ? formatTime(c.updated_at) : ""}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </PageContainer>
  );
}
