"use client";

import { Empty, Skeleton } from "antd";
import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useApiQuery } from "@/lib/api/hooks";

interface GraphNode {
  id: string;
  label: string;
  kind: string;
  meta?: Record<string, unknown>;
}

interface GraphEdge {
  from_id: string;
  to_id: string;
  relationship_type: string;
  ownership_pct?: number | null;
  meta?: Record<string, unknown>;
}

interface GraphPayload {
  root_id: string;
  depth: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

function radialLayout(nodes: GraphNode[], rootId: string): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {};
  positions[rootId] = { x: 0, y: 0 };
  const others = nodes.filter((n) => n.id !== rootId);
  const r = Math.max(220, others.length * 16);
  const step = (Math.PI * 2) / Math.max(1, others.length);
  others.forEach((n, i) => {
    positions[n.id] = {
      x: Math.cos(i * step) * r,
      y: Math.sin(i * step) * r,
    };
  });
  return positions;
}

export function RelationshipGraph({
  rootId,
  depth = 2,
  height = 420,
}: {
  rootId: string;
  depth?: number;
  height?: number;
}) {
  const graph = useApiQuery<GraphPayload>({
    queryKey: ["entities", "graph", rootId, depth],
    path: "/entities/graph",
    query: { root_id: rootId, depth },
    staleTime: 30_000,
  });

  const { rfNodes, rfEdges } = useMemo(() => {
    if (!graph.data) return { rfNodes: [] as Node[], rfEdges: [] as Edge[] };
    const positions = radialLayout(graph.data.nodes, rootId);
    const rfNodes: Node[] = graph.data.nodes.map((n) => ({
      id: n.id,
      position: positions[n.id] ?? { x: 0, y: 0 },
      data: { label: `${n.label}\n[${n.kind}]` },
      type: "default",
    }));
    const rfEdges: Edge[] = graph.data.edges.map((e, idx) => ({
      id: `${e.from_id}->${e.to_id}-${idx}`,
      source: e.from_id,
      target: e.to_id,
      label: e.ownership_pct
        ? `${e.relationship_type} (${(e.ownership_pct * 100).toFixed(1)}%)`
        : e.relationship_type,
      animated: e.relationship_type.includes("subsidiary"),
    }));
    return { rfNodes, rfEdges };
  }, [graph.data, rootId]);

  if (graph.isLoading || !graph.data) {
    return <Skeleton active />;
  }
  if (!graph.data.nodes.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No relationships found." />;
  }

  return (
    <div style={{ height, border: "1px solid var(--ant-color-border)", borderRadius: 6 }}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
