"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Tag, Typography } from "antd";
import type { ReactNode } from "react";

import type { AqpNode } from "./types";

const { Text } = Typography;

interface AqpNodeCardProps extends NodeProps<AqpNode> {
  accent?: string;
  icon?: ReactNode;
  badge?: ReactNode;
  /** When true the node has no incoming handle (sources). */
  source?: boolean;
  /** When true the node has no outgoing handle (sinks). */
  sink?: boolean;
}

export function AqpNodeCard(props: AqpNodeCardProps) {
  const { data, selected, accent = "#3b82f6", icon, badge, source, sink } = props;
  return (
    <div
      style={{
        background: "var(--ant-color-bg-elevated, #111827)",
        border: `1px solid ${selected ? accent : "var(--ant-color-border, #1f2937)"}`,
        borderLeft: `3px solid ${accent}`,
        borderRadius: 8,
        padding: "8px 12px",
        minWidth: 180,
        maxWidth: 240,
        boxShadow: selected ? `0 0 0 2px ${accent}33` : "0 1px 4px rgba(0,0,0,0.18)",
        fontSize: 12,
      }}
    >
      {!source ? (
        <Handle
          type="target"
          position={Position.Left}
          style={{ background: accent, width: 8, height: 8 }}
        />
      ) : null}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        {icon ? <span style={{ fontSize: 14 }}>{icon}</span> : null}
        <Tag color="default" style={{ marginInlineEnd: 0, fontSize: 10, padding: "0 6px" }}>
          {data.kind}
        </Tag>
        {badge}
      </div>
      <Text strong style={{ fontSize: 13, display: "block", marginBottom: 2 }}>
        {data.label ?? data.kind}
      </Text>
      {data.notes ? (
        <Text type="secondary" style={{ fontSize: 11 }}>
          {data.notes}
        </Text>
      ) : null}
      {!sink ? (
        <Handle
          type="source"
          position={Position.Right}
          style={{ background: accent, width: 8, height: 8 }}
        />
      ) : null}
    </div>
  );
}
