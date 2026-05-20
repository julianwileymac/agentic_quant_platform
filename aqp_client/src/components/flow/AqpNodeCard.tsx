import { Handle, Position, type NodeProps } from "@xyflow/react";
import { memo, useMemo } from "react";

import { cn } from "@/lib/utils";

import { DEFAULT_NODE_ACCENT, type AqpNode } from "./types";

interface AqpNodeCardProps extends NodeProps<AqpNode> {
  accent?: string;
}

/**
 * Custom React Flow node renderer. Uses our shadcn-styled tokens for
 * background / border so dark mode is consistent with the rest of the
 * app. Header strip uses the per-kind accent colour from the palette.
 */
function AqpNodeCardImpl(props: AqpNodeCardProps) {
  const { id: _id, data, selected, accent: accentProp, dragging } = props;
  const accent = data.accent ?? accentProp ?? DEFAULT_NODE_ACCENT;
  const summary = useMemo(() => summariseParams(data.params), [data.params]);

  return (
    <div
      className={cn(
        "min-w-[200px] max-w-[280px] rounded-md border bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-sm transition-shadow",
        selected ? "border-[var(--info-fg)] shadow-[0_0_0_1px_var(--info-fg)]" : "border-[var(--border-default)]",
        dragging && "opacity-90",
      )}
      data-flow-node="true"
      data-kind={data.kind}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !bg-[var(--info-fg)]" />
      <div
        className="flex items-center justify-between gap-2 rounded-t-md px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-white"
        style={{ background: accent }}
      >
        <span>{data.kind}</span>
        {data.notes ? (
          <span title={data.notes} className="rounded-sm bg-black/30 px-1 text-[9px] normal-case tracking-normal">
            note
          </span>
        ) : null}
      </div>
      <div className="px-3 py-2">
        <div className="text-sm font-medium leading-tight">{data.label ?? data.kind}</div>
        {summary ? (
          <p className="mt-1 line-clamp-2 break-words font-mono text-[10px] text-[var(--text-secondary)]">
            {summary}
          </p>
        ) : null}
      </div>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !bg-[var(--info-fg)]" />
    </div>
  );
}

export const AqpNodeCard = memo(AqpNodeCardImpl);

/**
 * One-line summary of a node's params for the card body. Picks the
 * first 2-3 entries; falls back to "(empty)" when no params are set.
 */
function summariseParams(params: Record<string, unknown> | undefined): string | null {
  if (!params) return null;
  const entries = Object.entries(params);
  if (!entries.length) return null;
  const parts: string[] = [];
  for (const [key, value] of entries.slice(0, 3)) {
    if (value == null) continue;
    if (typeof value === "string") {
      parts.push(`${key}=${truncate(value, 18)}`);
    } else if (typeof value === "number" || typeof value === "boolean") {
      parts.push(`${key}=${value}`);
    } else if (Array.isArray(value)) {
      parts.push(`${key}[${value.length}]`);
    } else if (typeof value === "object") {
      parts.push(`${key}{}`);
    }
  }
  return parts.join(" · ");
}

function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}
