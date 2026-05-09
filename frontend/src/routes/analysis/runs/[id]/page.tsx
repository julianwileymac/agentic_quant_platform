import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  type RunDetail,
  type StepResultSummary,
  getAnalysisRun,
  getAnalysisStepResults,
} from "@/lib/analysis/api";

export function AnalysisRunDetailRoute() {
  const params = useParams<{ id: string }>();
  const runId = params.id ?? "";
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeStep, setActiveStep] = useState<string | null>(null);
  const [stepRows, setStepRows] = useState<Array<Record<string, unknown>>>([]);
  const [stepLoading, setStepLoading] = useState(false);
  const [stepError, setStepError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    getAnalysisRun(runId)
      .then((res) => {
        setRun(res);
        const first = res.steps?.[0]?.step_alias;
        if (first) setActiveStep(first);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => {
    if (!runId || !activeStep) return;
    setStepLoading(true);
    setStepError(null);
    getAnalysisStepResults(runId, activeStep, 200)
      .then((res) => setStepRows(res.rows ?? []))
      .catch((err) =>
        setStepError(err instanceof Error ? err.message : String(err)),
      )
      .finally(() => setStepLoading(false));
  }, [runId, activeStep]);

  const activeStepRow = useMemo<StepResultSummary | null>(() => {
    if (!run || !activeStep) return null;
    return run.steps.find((s) => s.step_alias === activeStep) ?? null;
  }, [run, activeStep]);

  return (
    <PageContainer
      title={run ? `Run ${run.id.slice(0, 8)}` : "Analysis run"}
      subtitle={run?.dataset_descriptor ?? undefined}
      extra={
        run ? (
          <div className="flex items-center gap-2">
            <Badge variant={run.status === "completed" ? "secondary" : "outline"}>
              {run.status}
            </Badge>
            <Button asChild size="sm" variant="outline">
              <Link to="/analysis/runs">All runs</Link>
            </Button>
          </div>
        ) : null
      }
    >
      {loading ? (
        <p className="text-xs text-[var(--text-secondary)]">Loading...</p>
      ) : error ? (
        <p className="text-xs text-[var(--neg-fg)]">{error}</p>
      ) : !run ? (
        <p className="text-xs text-[var(--text-secondary)]">Run not found.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
          <aside className="space-y-2">
            <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 text-xs">
              <h3 className="mb-1 font-medium uppercase text-[var(--text-secondary)]">
                Run summary
              </h3>
              <dl className="space-y-1">
                <Row label="target" value={run.target} />
                <Row label="status" value={run.status} />
                <Row label="task" value={run.task_id ?? "—"} />
                <Row label="started" value={run.started_at} />
                <Row label="ended" value={run.ended_at ?? "—"} />
                <Row label="error" value={run.error ?? "—"} />
              </dl>
            </div>
            <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2">
              <h3 className="mb-2 px-1 text-xs font-medium uppercase text-[var(--text-secondary)]">
                Steps ({run.steps.length})
              </h3>
              <div className="flex flex-col gap-1">
                {run.steps.map((step) => (
                  <button
                    key={step.id}
                    type="button"
                    onClick={() => setActiveStep(step.step_alias)}
                    className={`flex flex-col items-start gap-0.5 rounded-md px-2 py-1.5 text-left text-xs transition ${
                      activeStep === step.step_alias
                        ? "bg-[var(--bg-elevated)] text-[var(--text-primary)]"
                        : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
                    }`}
                  >
                    <span className="font-medium">{step.step_alias}</span>
                    <span className="font-mono text-[10px] opacity-70">
                      {step.flow}
                    </span>
                    <span
                      className={`text-[10px] uppercase ${
                        step.status === "error"
                          ? "text-[var(--neg-fg)]"
                          : "text-[var(--text-secondary)]"
                      }`}
                    >
                      {step.status}
                      {step.duration_ms
                        ? ` · ${Math.round(step.duration_ms)}ms`
                        : ""}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </aside>
          <section className="space-y-3">
            {activeStepRow ? (
              <>
                <header className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-medium">
                      {activeStepRow.step_alias}
                    </h2>
                    <p className="font-mono text-[10px] text-[var(--text-secondary)]">
                      {activeStepRow.flow}
                    </p>
                  </div>
                  {activeStepRow.artifact_uri ? (
                    <Badge variant="secondary">
                      {activeStepRow.artifact_uri}
                    </Badge>
                  ) : null}
                </header>
                <MetricsGrid metrics={activeStepRow.metrics_json} />
                <div>
                  <h3 className="mb-1 text-xs font-medium uppercase text-[var(--text-secondary)]">
                    Iceberg preview
                  </h3>
                  {stepLoading ? (
                    <p className="text-xs text-[var(--text-secondary)]">
                      Loading rows...
                    </p>
                  ) : stepError ? (
                    <p className="text-xs text-[var(--neg-fg)]">{stepError}</p>
                  ) : stepRows.length === 0 ? (
                    <p className="text-xs text-[var(--text-secondary)]">
                      No persisted rows for this step.
                    </p>
                  ) : (
                    <div className="max-h-[400px] overflow-auto rounded-md border border-[var(--border-default)]">
                      <table className="w-full text-xs">
                        <thead className="sticky top-0 bg-[var(--bg-elevated)]">
                          <tr>
                            {Object.keys(stepRows[0]!).map((col) => (
                              <th
                                key={col}
                                className="px-2 py-1 text-left font-medium"
                              >
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {stepRows.map((row, idx) => (
                            <tr
                              key={idx}
                              className="border-t border-[var(--border-default)]"
                            >
                              {Object.keys(stepRows[0]!).map((col) => (
                                <td key={col} className="px-2 py-1 font-mono">
                                  {String(row[col] ?? "—")}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <p className="text-xs text-[var(--text-secondary)]">
                Pick a step on the left to inspect its metrics + Iceberg output.
              </p>
            )}
          </section>
        </div>
      )}
    </PageContainer>
  );
}

function Row({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-[var(--text-secondary)]">{label}</dt>
      <dd className="font-mono">{value ?? "—"}</dd>
    </div>
  );
}

function MetricsGrid({ metrics }: { metrics: Record<string, unknown> }) {
  const entries = Object.entries(metrics ?? {});
  if (entries.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="flex flex-col rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2"
        >
          <span className="text-[10px] text-[var(--text-secondary)]">{key}</span>
          <span className="font-mono text-sm">
            {typeof value === "number" || typeof value === "string"
              ? String(value)
              : JSON.stringify(value)}
          </span>
        </div>
      ))}
    </div>
  );
}
