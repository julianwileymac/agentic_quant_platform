"use client";

import { Progress, Tag } from "antd";
import { ScrollText } from "lucide-react";

import { useCeleryTask } from "@/hooks/useCeleryTask";
import { useTelemetryStore } from "@/stores/telemetry";

interface TaskStreamerProps {
  taskId: string | null;
}

/**
 * Renders live Celery task telemetry.
 *
 * AGENTS rule 9: frames preserve {task_id, stage, message, timestamp, **extras}.
 * The hook pushes frames into useTelemetryStore (ring buffer, bounded to 5k).
 */
export function TaskStreamer({ taskId }: TaskStreamerProps) {
  const { status } = useCeleryTask(taskId);
  const frames = useTelemetryStore((s) =>
    taskId ? (s.byTask[taskId] ?? []) : [],
  );

  if (!taskId) {
    return (
      <div className="text-sm" style={{ color: "var(--text-muted)" }}>
        No active task.
      </div>
    );
  }

  const latest = frames[frames.length - 1];
  const pct = typeof latest?.pct === "number" ? Math.max(0, Math.min(100, latest.pct)) : undefined;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm">
          <Tag color={statusColor(status)}>{status.toUpperCase()}</Tag>
          <code style={{ color: "var(--text-muted)" }}>{taskId.slice(0, 12)}</code>
          {latest?.stage ? (
            <span style={{ color: "var(--text-secondary)" }}>{latest.stage}</span>
          ) : null}
        </div>
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          {frames.length} frame{frames.length === 1 ? "" : "s"}
        </div>
      </div>

      {pct !== undefined ? <Progress percent={pct} size="small" /> : null}

      <div
        className="max-h-80 overflow-y-auto rounded border p-3 font-mono text-xs"
        style={{
          background: "var(--bg-elevated)",
          borderColor: "var(--border-default)",
          color: "var(--text-secondary)",
        }}
      >
        {frames.length === 0 ? (
          <div className="flex items-center gap-2" style={{ color: "var(--text-muted)" }}>
            <ScrollText size={14} />
            Waiting for first frame…
          </div>
        ) : (
          frames.slice(-200).map((frame, idx) => (
            <div key={`${frame.timestamp}-${idx}`} className="leading-tight">
              <span style={{ color: "var(--text-muted)" }}>
                {frame.timestamp ? new Date(frame.timestamp).toLocaleTimeString() : "—"}
              </span>{" "}
              <span style={{ color: "var(--accent-primary)" }}>{frame.stage ?? "log"}</span>{" "}
              {String(frame.message ?? "")}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function statusColor(status: string): string {
  switch (status) {
    case "open":
      return "blue";
    case "closed":
      return "default";
    case "error":
      return "red";
    case "connecting":
      return "geekblue";
    default:
      return "default";
  }
}
