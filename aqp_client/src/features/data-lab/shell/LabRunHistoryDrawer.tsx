import { ChevronUp, History, RotateCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import {
  type LabRunOut,
  listLabRuns,
  reproduceLabRun,
} from "@/lib/api/lab";

import { useLabStore } from "../state/labStore";
import type { LabServerEnvelope } from "../ws/envelopes";

interface NodeLane {
  nodeId: string;
  events: Array<{ ts: number; state: string; message: string }>;
  metrics: Record<string, unknown>;
  lastError?: string | null;
  lastState: string;
}

function laneAccentForState(state: string): string {
  if (state === "done") return "bg-emerald-500";
  if (state === "error") return "bg-rose-500";
  if (state === "halted" || state === "cancelled") return "bg-amber-500";
  if (state === "running") return "bg-sky-500";
  return "bg-muted";
}

function buildLanes(envelopes: LabServerEnvelope[]): NodeLane[] {
  const byNode: Record<string, NodeLane> = {};
  for (const env of envelopes) {
    if (env.kind === "run.status" && env.node_id) {
      const lane = byNode[env.node_id] ?? {
        nodeId: env.node_id,
        events: [],
        metrics: {},
        lastState: "pending",
      };
      lane.events.push({
        ts: env.timestamp,
        state: env.state,
        message: env.message,
      });
      lane.lastState = env.state;
      byNode[env.node_id] = lane;
    } else if (env.kind === "run.metric" && env.node_id) {
      const lane = byNode[env.node_id] ?? {
        nodeId: env.node_id,
        events: [],
        metrics: {},
        lastState: "pending",
      };
      lane.metrics[env.name] = env.value;
      byNode[env.node_id] = lane;
    } else if (env.kind === "run.log" && env.level === "error" && env.node_id) {
      const lane = byNode[env.node_id] ?? {
        nodeId: env.node_id,
        events: [],
        metrics: {},
        lastState: "pending",
      };
      lane.lastError = env.msg;
      byNode[env.node_id] = lane;
    }
  }
  return Object.values(byNode);
}

/**
 * Run history drawer — Grafana-style timeline at the bottom of the
 * LabShell. One swimlane per node; lane colour is keyed to the
 * latest run.status state. Updates live from the WS envelope ring
 * in :class:`labStore`.
 */
export function LabRunHistoryDrawer() {
  const [open, setOpen] = useState(false);
  const [recentRuns, setRecentRuns] = useState<LabRunOut[]>([]);
  const [reproducingRunId, setReproducingRunId] = useState<string | null>(null);
  const envelopes = useLabStore((s) => s.recentEnvelopes);
  const currentRun = useLabStore((s) => s.currentRun);
  const setCurrentRun = useLabStore((s) => s.setCurrentRun);
  const labId = useLabStore((s) => s.labId);

  const lanes = useMemo(() => buildLanes(envelopes), [envelopes]);
  const runningCount = lanes.filter((l) => l.lastState === "running").length;
  const errorCount = lanes.filter((l) => l.lastState === "error").length;

  // Refresh the recent-runs list every time the drawer opens + after
  // each WS terminal frame (done / error / halted) so the historical
  // pane stays in sync with the swimlane.
  const refresh = useCallback(() => {
    if (!labId) {
      setRecentRuns([]);
      return;
    }
    void listLabRuns({ labId, limit: 25 })
      .then(setRecentRuns)
      .catch(() => setRecentRuns([]));
  }, [labId]);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (!currentRun) return;
    if (
      currentRun.status === "done" ||
      currentRun.status === "error" ||
      currentRun.status === "halted" ||
      currentRun.status === "cancelled"
    ) {
      refresh();
    }
  }, [currentRun, refresh]);

  const handleReproduce = useCallback(
    async (run: LabRunOut) => {
      setReproducingRunId(run.id);
      try {
        const reply = await reproduceLabRun(run.id);
        toast.success(
          `Reproducing run ${run.id.slice(0, 8)}… → new run ${reply.new_run_id.slice(0, 8)}…`,
        );
        // Hook into the active run slot so the swimlane + content-hash
        // badge update without waiting for the next refresh tick.
        setCurrentRun({
          ...run,
          id: reply.new_run_id,
          task_id: reply.new_task_id,
          status: "queued",
          started_at: new Date().toISOString(),
          ended_at: null,
          duration_ms: null,
        });
        refresh();
      } catch (err) {
        toast.error(
          `Reproduce failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      } finally {
        setReproducingRunId(null);
      }
    },
    [refresh, setCurrentRun],
  );

  if (!open) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="fixed bottom-3 right-3 z-30 gap-2 shadow-lg"
      >
        <History className="h-4 w-4" /> Run history
        {runningCount > 0 ? (
          <Badge variant="secondary">{runningCount} running</Badge>
        ) : null}
        {errorCount > 0 ? (
          <Badge variant="negative">{errorCount} error</Badge>
        ) : null}
      </Button>
    );
  }

  return (
    <Card className="fixed bottom-3 left-3 right-3 z-30 max-h-96 overflow-hidden shadow-2xl">
      <CardContent className="space-y-2 py-2">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4" />
          <span className="text-sm font-medium">Run history</span>
          {currentRun ? (
            <Badge variant="outline" className="font-mono">
              {currentRun.id.slice(0, 8)}…
            </Badge>
          ) : null}
          <div className="flex-1" />
          <Button variant="ghost" size="sm" onClick={refresh} className="gap-1">
            <RotateCw className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)} className="gap-2">
            <ChevronUp className="h-4 w-4" /> Collapse
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)} className="gap-1">
            <X className="h-4 w-4" />
          </Button>
        </div>
        {recentRuns.length > 0 ? (
          <div className="max-h-32 overflow-y-auto rounded border border-border/40">
            <table className="min-w-full text-[11px]">
              <thead className="sticky top-0 bg-background">
                <tr className="text-left text-muted-foreground">
                  <th className="px-2 py-1">run</th>
                  <th className="px-2 py-1">mode</th>
                  <th className="px-2 py-1">status</th>
                  <th className="px-2 py-1">started</th>
                  <th className="px-2 py-1">hash</th>
                  <th className="px-2 py-1 text-right">actions</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map((run) => (
                  <tr
                    key={run.id}
                    className={`odd:bg-muted/20 ${
                      currentRun?.id === run.id ? "bg-sky-500/5" : ""
                    }`}
                  >
                    <td className="px-2 py-1 font-mono">{run.id.slice(0, 8)}</td>
                    <td className="px-2 py-1">{run.mode}</td>
                    <td className="px-2 py-1">
                      <Badge
                        variant={
                          run.status === "done"
                            ? "positive"
                            : run.status === "error"
                              ? "negative"
                              : run.status === "halted" ||
                                  run.status === "cancelled"
                                ? "warn"
                                : "secondary"
                        }
                      >
                        {run.status}
                      </Badge>
                    </td>
                    <td className="px-2 py-1 font-mono text-muted-foreground">
                      {new Date(run.started_at).toLocaleTimeString()}
                    </td>
                    <td
                      className="px-2 py-1 font-mono text-muted-foreground"
                      title={run.content_hash}
                    >
                      {run.content_hash.slice(0, 8)}
                    </td>
                    <td className="px-2 py-1 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 gap-1 px-2 text-[10px]"
                        disabled={
                          reproducingRunId === run.id ||
                          run.status === "running" ||
                          run.status === "queued"
                        }
                        onClick={() => handleReproduce(run)}
                        title={
                          run.status === "running" || run.status === "queued"
                            ? "Cannot reproduce while the run is still active."
                            : "Re-dispatch this run with its pinned snapshot triple."
                        }
                      >
                        <RotateCw className="h-3 w-3" />
                        {reproducingRunId === run.id ? "Reproducing…" : "Reproduce"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="max-h-52 space-y-1 overflow-y-auto pr-2 text-xs">
          {lanes.length === 0 ? (
            <div className="text-muted-foreground">
              No WS envelopes received yet. Run a graph and the per-node
              swimlanes will populate here.
            </div>
          ) : (
            lanes.map((lane) => (
              <div
                key={lane.nodeId}
                className="grid grid-cols-[100px_1fr_auto] items-center gap-2"
              >
                <code className="truncate font-mono text-[11px]">{lane.nodeId}</code>
                <div className="relative h-3 rounded bg-muted/40">
                  {lane.events.length === 0 ? null : (
                    <div
                      className={`absolute inset-y-0 left-0 rounded ${laneAccentForState(
                        lane.lastState,
                      )}`}
                      style={{
                        width: `${Math.min(100, lane.events.length * 5)}%`,
                      }}
                      title={`${lane.events.length} events — last state ${lane.lastState}`}
                    />
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <Badge
                    variant={
                      lane.lastState === "done"
                        ? "positive"
                        : lane.lastState === "error"
                          ? "negative"
                          : "secondary"
                    }
                  >
                    {lane.lastState}
                  </Badge>
                  {Object.entries(lane.metrics).length > 0 ? (
                    <Badge variant="outline">
                      {Object.entries(lane.metrics)
                        .slice(0, 3)
                        .map(([k, v]) => `${k}=${String(v).slice(0, 6)}`)
                        .join(" ")}
                    </Badge>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default LabRunHistoryDrawer;
