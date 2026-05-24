import { Activity, Code2, FlaskConical, GitBranch, Telescope } from "lucide-react";
import { type ReactNode, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { LabMode } from "@/lib/api/lab";

import { DataBrowser } from "../catalog/DataBrowser";
import { PaperRagDrawer } from "../papers/PaperRagDrawer";
import { useLabStore } from "../state/labStore";
import { TestingInspectorRail } from "../testing/TestingInspectorRail";
import { useLabChannel } from "../ws/useLabChannel";
import { LabRunHistoryDrawer } from "./LabRunHistoryDrawer";

const MODE_TABS: Array<{
  id: LabMode;
  label: string;
  description: string;
  icon: typeof Activity;
}> = [
  {
    id: "eda",
    label: "EDA",
    description: "Reactive cell notebook for exploratory analysis.",
    icon: Telescope,
  },
  {
    id: "testing",
    label: "Testing",
    description: "React Flow graph editor for backtests and feature studies.",
    icon: GitBranch,
  },
  {
    id: "evaluation",
    label: "Evaluation",
    description: "Parameter sweeps with Combinatorial Purged CV + Deflated Sharpe.",
    icon: FlaskConical,
  },
  {
    id: "simulation",
    label: "Simulation",
    description: "hftbacktest / JAX optimal control / RL env replay + live streams.",
    icon: Activity,
  },
];

interface LabShellProps {
  /** The active mode's main pane (route child). */
  children: ReactNode;
  /** Optional left rail content; defaults to the Catalog (DataBrowser). */
  leftRail?: ReactNode;
  /** Optional right rail content; defaults to the Inspector. */
  rightRail?: ReactNode;
}

/**
 * Four-mode workspace shell mounted at `/labs/[lab_id]/workspace`.
 *
 * Owns:
 * - The mode-tab bar (top).
 * - Graph name + content-hash badge.
 * - The persistent left rail (Catalog) and right rail (Inspector / RAG drawer).
 * - The bottom Run History drawer slot.
 * - The /ws/lab/{session_id} subscription that pumps typed Lab envelopes
 *   into the Zustand store.
 *
 * Sub-pages render inside `children`. Each mode renders its own canvas,
 * cell stack, sweep grid, or simulation panes inside this shell.
 */
export function LabShell({ children, leftRail, rightRail }: LabShellProps) {
  const { lab_id: routeLabId } = useParams<{ lab_id: string }>();
  const navigate = useNavigate();
  const labId = useLabStore((s) => s.labId);
  const mode = useLabStore((s) => s.mode);
  const sessionId = useLabStore((s) => s.sessionId);
  const draftGraph = useLabStore((s) => s.draftGraph);
  const currentRun = useLabStore((s) => s.currentRun);
  const setLabId = useLabStore((s) => s.setLabId);
  const setMode = useLabStore((s) => s.setMode);
  const pushEnvelope = useLabStore((s) => s.pushEnvelope);

  useEffect(() => {
    if (routeLabId && routeLabId !== labId) {
      setLabId(routeLabId);
    }
  }, [routeLabId, labId, setLabId]);

  // Multiplexed Lab WS. The hook handles auth + reconnect + backoff
  // by delegating to createWsClient under the hood; we only need to
  // drain envelopes into the Zustand store.
  const channel = useLabChannel({
    sessionId,
    onEnvelope: pushEnvelope,
  });

  const handleModeChange = (next: LabMode) => {
    setMode(next);
    if (routeLabId) {
      navigate(`/labs/${routeLabId}/workspace/${next}`);
    }
  };

  const contentHashShort = draftGraph?.content_hash?.slice(0, 12);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Card className="rounded-none border-b border-x-0 border-t-0">
        <CardContent className="flex flex-wrap items-center gap-3 py-3">
          <div className="flex flex-col">
            <div className="text-sm font-medium leading-none">
              {draftGraph?.name ?? "Data Lab"}
            </div>
            <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
              {contentHashShort ? (
                <Badge variant="outline" className="font-mono">
                  {contentHashShort}
                </Badge>
              ) : (
                <span>No graph loaded.</span>
              )}
              {currentRun ? (
                <Badge
                  variant={
                    currentRun.status === "done"
                      ? "positive"
                      : currentRun.status === "error"
                        ? "negative"
                        : currentRun.status === "halted" ||
                            currentRun.status === "cancelled"
                          ? "warn"
                          : "secondary"
                  }
                >
                  run: {currentRun.status}
                </Badge>
              ) : null}
              <span
                className={
                  channel.status === "open" ? "text-emerald-500" : "text-muted-foreground"
                }
                title={`Lab WS: ${channel.status}`}
              >
                ws: {channel.status}
              </span>
            </div>
          </div>

          <div className="flex-1" />

          <Tabs
            value={mode}
            onValueChange={(v) => handleModeChange(v as LabMode)}
          >
            <TabsList className="bg-muted/30">
              {MODE_TABS.map((m) => {
                const Icon = m.icon;
                return (
                  <TabsTrigger key={m.id} value={m.id} title={m.description} className="gap-2">
                    <Icon className="h-4 w-4" />
                    {m.label}
                  </TabsTrigger>
                );
              })}
            </TabsList>
          </Tabs>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/admin/labs")}
            className="gap-2"
          >
            <Code2 className="h-4 w-4" />
            Manage Labs
          </Button>
        </CardContent>
      </Card>

      <div className="flex min-h-0 flex-1">
        <aside className="w-64 shrink-0 overflow-y-auto border-r p-2">
          {leftRail !== undefined ? leftRail : <DataBrowser />}
        </aside>
        <main className="min-h-0 min-w-0 flex-1 overflow-hidden p-2">
          {children}
        </main>
        <aside className="w-80 shrink-0 overflow-y-auto border-l p-2">
          {rightRail !== undefined
            ? rightRail
            : mode === "testing"
              ? <TestingInspectorRail />
              : <PaperRagDrawer />}
        </aside>
      </div>
      <LabRunHistoryDrawer />
    </div>
  );
}

export { MODE_TABS };
