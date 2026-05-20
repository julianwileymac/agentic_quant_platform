import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  Circle,
  CircleAlert,
  CircleDot,
  Loader2,
  Wrench,
} from "lucide-react";
import { type ComponentType, type ReactNode, useEffect, useMemo, useRef } from "react";

import { Badge } from "@/components/ui/badge";
import { cn, formatTime } from "@/lib/utils";
import type { ProgressEvent } from "@/lib/ws/types";

interface ProgressTimelineProps {
  events: ProgressEvent[];
  /** Stick to the bottom on new events (chat-style). Default true. */
  follow?: boolean;
  /** Fixed height for the virtualized scroller. */
  height?: number | string;
  /** Optional click handler — used by Crew Trace to filter by stage. */
  onSelectEvent?: (event: ProgressEvent, index: number) => void;
  /** Optional empty state text. */
  emptyState?: ReactNode;
  className?: string;
}

interface StageMeta {
  icon: ComponentType<{ className?: string }>;
  /** Background tint for the icon bubble. */
  tone: "info" | "positive" | "negative" | "warn" | "muted";
}

const STAGE_META: Record<string, StageMeta> = {
  starting: { icon: CircleDot, tone: "info" },
  running: { icon: Loader2, tone: "info" },
  thinking: { icon: Brain, tone: "info" },
  tool: { icon: Wrench, tone: "muted" },
  done: { icon: CheckCircle2, tone: "positive" },
  error: { icon: CircleAlert, tone: "negative" },
  cancelled: { icon: AlertTriangle, tone: "warn" },
};

const TONE_CLASSES: Record<StageMeta["tone"], string> = {
  info: "bg-[var(--info-bg)] text-[var(--info-fg)] border-[var(--info-fg)]",
  positive: "bg-[var(--pos-bg)] text-[var(--pos-fg)] border-[var(--pos-fg)]",
  negative: "bg-[var(--neg-bg)] text-[var(--neg-fg)] border-[var(--neg-fg)]",
  warn: "bg-[var(--warn-bg)] text-[var(--warn-fg)] border-[var(--warn-fg)]",
  muted: "bg-[var(--bg-elevated)] text-[var(--text-secondary)] border-[var(--border-default)]",
};

const FALLBACK_META: StageMeta = { icon: Circle, tone: "muted" };

/**
 * Vertical streaming-progress timeline. Designed for the Celery /
 * agent progress stream relayed over `useChatStream`. Each entry
 * shows a stage icon, agent / tool name, message, and tabular
 * timestamp. The list is virtualized so a 10k-event run remains
 * smooth.
 *
 * The blueprint mandates that consequential agent reasoning is
 * inspectable end-to-end — this is the canvas every agent / crew /
 * ML training surface uses to surface live progress.
 */
export function ProgressTimeline({
  events,
  follow = true,
  height = 360,
  onSelectEvent,
  emptyState,
  className,
}: ProgressTimelineProps) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const virtualizer = useVirtualizer({
    count: events.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 60,
    overscan: 8,
  });

  // Auto-scroll to the latest event when `follow` is enabled.
  useEffect(() => {
    if (!follow || events.length === 0) return;
    virtualizer.scrollToIndex(events.length - 1, { align: "end" });
  }, [events.length, follow, virtualizer]);

  const styleHeight = useMemo<string | number>(
    () => (typeof height === "number" ? height : height),
    [height],
  );

  if (events.length === 0) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-md border border-dashed border-[var(--border-default)] text-sm text-[var(--text-secondary)]",
          className,
        )}
        style={{ height: styleHeight }}
      >
        {emptyState ?? "Waiting for events…"}
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      className={cn("relative overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)]", className)}
      style={{ height: styleHeight }}
    >
      <div style={{ height: virtualizer.getTotalSize(), width: "100%", position: "relative" }}>
        {virtualizer.getVirtualItems().map((row) => {
          const event = events[row.index];
          if (!event) return null;
          const stage = (event.stage ?? "running").toString();
          const meta = STAGE_META[stage] ?? FALLBACK_META;
          const Icon = meta.icon;
          const tone = TONE_CLASSES[meta.tone];
          const ts = event.timestamp ?? (event.ts as string | undefined);
          const message =
            event.message ?? (typeof event.content === "string" ? event.content : undefined);
          const interactive = Boolean(onSelectEvent);
          return (
            <div
              key={`${row.index}-${ts ?? "nots"}`}
              style={{
                position: "absolute",
                top: row.start,
                left: 0,
                width: "100%",
                minHeight: row.size,
              }}
              className={cn(
                "flex gap-3 border-b border-[var(--border-subtle)] px-4 py-2",
                interactive && "cursor-pointer hover:bg-[var(--bg-elevated)]",
              )}
              onClick={interactive ? () => onSelectEvent?.(event, row.index) : undefined}
              onKeyDown={
                interactive
                  ? (e) => {
                      if (e.key === "Enter") onSelectEvent?.(event, row.index);
                    }
                  : undefined
              }
              role={interactive ? "button" : "listitem"}
              tabIndex={interactive ? 0 : -1}
            >
              <div
                className={cn(
                  "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
                  tone,
                )}
              >
                <Icon className={cn("h-3.5 w-3.5", stage === "running" && "animate-spin")} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono uppercase tracking-wider text-[var(--text-secondary)]">
                    {stage}
                  </span>
                  {event.agent ? (
                    <Badge variant="secondary" className="text-[10px]">
                      {event.agent}
                    </Badge>
                  ) : null}
                  {event.tool ? (
                    <Badge variant="outline" className="text-[10px]">
                      tool: {event.tool}
                    </Badge>
                  ) : null}
                  <span className="ml-auto font-mono tabular-nums text-[var(--text-muted)]">
                    {ts ? formatTime(ts) : ""}
                  </span>
                </div>
                {message ? (
                  <p className="mt-0.5 break-words text-sm text-[var(--text-primary)]">
                    {message}
                  </p>
                ) : null}
                {event.delta ? (
                  <p className="mt-0.5 whitespace-pre-wrap break-words font-mono text-xs text-[var(--text-secondary)]">
                    {event.delta}
                  </p>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Convenience helper that groups an event stream by stage. Used by
 * the Crew Trace sidebar to summarise per-stage event counts.
 */
export function groupByStage(events: ProgressEvent[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const e of events) {
    const stage = (e.stage ?? "unknown").toString();
    out[stage] = (out[stage] ?? 0) + 1;
  }
  return out;
}
