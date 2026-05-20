import { Bot, Brain, Briefcase, RefreshCcw, Search, Telescope } from "lucide-react";
import { type ComponentType, useMemo, useState } from "react";

import { groupByStage, ProgressTimeline } from "@/components/common/ProgressTimeline";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useChatStream } from "@/lib/ws";
import { cn } from "@/lib/utils";

const STAGE_GROUPS: Array<{ id: string; label: string; icon: ComponentType<{ className?: string }>; match: (stage: string) => boolean }> = [
  { id: "researcher", label: "Researcher", icon: Telescope, match: (s) => s.includes("research") },
  { id: "selector", label: "Selector", icon: Brain, match: (s) => s.includes("select") },
  { id: "trader", label: "Trader", icon: Briefcase, match: (s) => s.includes("trade") || s.includes("trader") },
  { id: "analysis", label: "Analysis", icon: Bot, match: (s) => s.includes("analysis") || s.includes("analyst") },
];

export function CrewTraceRoute() {
  const [pendingTaskId, setPendingTaskId] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);

  const stream = useChatStream(taskId, "chat");

  const stageCounts = useMemo(() => groupByStage(stream.events), [stream.events]);
  const groupCounts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const grp of STAGE_GROUPS) {
      let count = 0;
      for (const event of stream.events) {
        const stage = (event.stage ?? "").toLowerCase();
        const agent = (event.agent ?? "").toLowerCase();
        if (grp.match(stage) || grp.match(agent)) count += 1;
      }
      out[grp.id] = count;
    }
    return out;
  }, [stream.events]);

  const filteredEvents = useMemo(() => {
    if (!activeGroup) return stream.events;
    const grp = STAGE_GROUPS.find((g) => g.id === activeGroup);
    if (!grp) return stream.events;
    return stream.events.filter((e) => {
      const stage = (e.stage ?? "").toLowerCase();
      const agent = (e.agent ?? "").toLowerCase();
      return grp.match(stage) || grp.match(agent);
    });
  }, [stream.events, activeGroup]);

  return (
    <PageContainer
      title="Crew Trace"
      subtitle="Live agent-pipeline viewer. Subscribe to any task_id to watch the LangGraph + spec-driven crew stream events in real time."
      extra={
        <Button variant="ghost" size="sm" onClick={stream.reset} disabled={!taskId}>
          <RefreshCcw className="h-4 w-4" /> Reset
        </Button>
      }
    >
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 py-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="crew-task">Task id</Label>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setTaskId(pendingTaskId.trim() || null);
                setActiveGroup(null);
              }}
            >
              <Input
                id="crew-task"
                value={pendingTaskId}
                onChange={(e) => setPendingTaskId(e.target.value)}
                placeholder="paste a Celery task_id"
                className="w-80 font-mono"
              />
              <Button type="submit" disabled={!pendingTaskId.trim()} className="gap-2">
                <Search className="h-4 w-4" /> Subscribe
              </Button>
            </form>
          </div>
          <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
            <Badge variant={stream.status === "open" ? "positive" : stream.status === "connecting" ? "warn" : "secondary"}>
              WS {stream.status}
            </Badge>
            <span>
              <span className="font-mono">{stream.events.length}</span> events ·{" "}
              {Object.keys(stageCounts).length} unique stages
            </span>
          </div>
        </CardContent>
      </Card>

      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-[220px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Stages</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1 p-2">
            <button
              type="button"
              onClick={() => setActiveGroup(null)}
              className={cn(
                "flex items-center justify-between rounded-md px-2 py-1.5 text-left text-sm",
                activeGroup == null ? "bg-[var(--info-bg)] text-[var(--info-fg)]" : "hover:bg-[var(--bg-elevated)]",
              )}
            >
              <span>All</span>
              <Badge variant="secondary">{stream.events.length}</Badge>
            </button>
            {STAGE_GROUPS.map((g) => {
              const Icon = g.icon;
              const active = activeGroup === g.id;
              return (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => setActiveGroup(g.id)}
                  className={cn(
                    "flex items-center justify-between rounded-md px-2 py-1.5 text-left text-sm",
                    active ? "bg-[var(--info-bg)] text-[var(--info-fg)]" : "hover:bg-[var(--bg-elevated)]",
                  )}
                >
                  <span className="flex items-center gap-2">
                    <Icon className="h-3.5 w-3.5" />
                    {g.label}
                  </span>
                  <Badge variant="secondary">{groupCounts[g.id] ?? 0}</Badge>
                </button>
              );
            })}
          </CardContent>
        </Card>

        <ProgressTimeline events={filteredEvents} height={"calc(100vh - 320px)"} follow />
      </div>
    </PageContainer>
  );
}
