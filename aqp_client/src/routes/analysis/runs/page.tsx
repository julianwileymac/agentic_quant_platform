import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { type RunSummary, listAnalysisRuns } from "@/lib/analysis/api";

const STATUS_TONE: Record<string, string> = {
  completed: "bg-[var(--pos-bg)] text-[var(--pos-fg)]",
  running: "bg-[var(--info-bg)] text-[var(--info-fg)]",
  pending: "bg-[var(--warn-bg)] text-[var(--warn-fg)]",
  error: "bg-[var(--neg-bg)] text-[var(--neg-fg)]",
};

export function AnalysisRunsRoute() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    listAnalysisRuns({ limit: 100 })
      .then((res) => setRuns(res))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <PageContainer
      title="Analysis Runs"
      subtitle="Hash-locked AnalysisSpec executions with per-step gold-tier Iceberg outputs."
      extra={
        <div className="flex items-center gap-2">
          <Badge variant="secondary">{runs.length} runs</Badge>
          <Button size="sm" variant="outline" onClick={refresh} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </Button>
          <Button asChild size="sm">
            <Link to="/analysis/lab">Back to Lab</Link>
          </Button>
        </div>
      }
    >
      {error ? (
        <p className="text-xs text-[var(--neg-fg)]">{error}</p>
      ) : loading ? (
        <p className="text-xs text-[var(--text-secondary)]">Loading...</p>
      ) : runs.length === 0 ? (
        <p className="text-xs text-[var(--text-secondary)]">
          No runs yet — kick one off from the Composer.
        </p>
      ) : (
        <div className="overflow-auto rounded-md border border-[var(--border-default)]">
          <table className="w-full text-xs">
            <thead className="bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
              <tr>
                <th className="px-3 py-1.5 text-left">id</th>
                <th className="px-3 py-1.5 text-left">target</th>
                <th className="px-3 py-1.5 text-left">status</th>
                <th className="px-3 py-1.5 text-left">dataset</th>
                <th className="px-3 py-1.5 text-left">started</th>
                <th className="px-3 py-1.5 text-left">ended</th>
                <th className="px-3 py-1.5"></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  className="border-t border-[var(--border-default)]"
                >
                  <td className="px-3 py-1.5 font-mono">{run.id.slice(0, 8)}</td>
                  <td className="px-3 py-1.5">{run.target}</td>
                  <td className="px-3 py-1.5">
                    <span
                      className={`rounded-sm px-2 py-0.5 text-[10px] uppercase ${
                        STATUS_TONE[run.status] ?? "bg-[var(--bg-elevated)]"
                      }`}
                    >
                      {run.status}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[var(--text-secondary)]">
                    {run.dataset_descriptor ?? "—"}
                  </td>
                  <td className="px-3 py-1.5">{formatTs(run.started_at)}</td>
                  <td className="px-3 py-1.5">{formatTs(run.ended_at)}</td>
                  <td className="px-3 py-1.5">
                    <Button asChild size="sm" variant="outline">
                      <Link to={`/analysis/runs/${run.id}`}>Open</Link>
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageContainer>
  );
}

function formatTs(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}
