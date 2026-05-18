import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useMemo } from "react";

import "@xyflow/react/dist/style.css";

import type {
  EntityLineagePayload,
  LineageEdgeWire,
} from "@/lib/api/metadata-aspects";
import { cn } from "@/lib/utils";

interface MetadataLineageGraphProps {
  lineage: EntityLineagePayload | null;
  className?: string;
  compact?: boolean;
}

const COLUMN_GAP = 260;
const ROW_GAP = 96;

export function MetadataLineageGraph({
  lineage,
  className,
  compact = false,
}: MetadataLineageGraphProps) {
  const graph = useMemo(() => buildGraph(lineage), [lineage]);
  if (!lineage) {
    return (
      <div
        className={cn(
          "flex h-[320px] items-center justify-center rounded-md border border-[var(--border-default)] text-sm text-[var(--text-muted)]",
          className,
        )}
      >
        No lineage data available.
      </div>
    );
  }

  return (
    <div
      className={cn(
        "w-full overflow-hidden rounded-md border border-[var(--border-default)]",
        compact ? "h-[320px]" : "h-[520px]",
        className,
      )}
    >
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={18}
          size={1}
          color="#334155"
        />
        <Controls showInteractive={false} />
        {compact ? null : (
          <MiniMap
            pannable
            zoomable
            maskColor="rgba(15, 23, 42, 0.8)"
            nodeColor={(node) =>
              node.id === lineage.entity ? "#0ea5e9" : "#64748b"
            }
          />
        )}
      </ReactFlow>
    </div>
  );
}

function buildGraph(lineage: EntityLineagePayload | null): {
  nodes: Node[];
  edges: Edge[];
} {
  if (!lineage) {
    return { nodes: [], edges: [] };
  }
  const uniqueEdges = new Map<string, LineageEdgeWire>();
  for (const edge of [...lineage.upstream_edges, ...lineage.downstream_edges]) {
    uniqueEdges.set(
      `${edge.from_entity}|${edge.to_entity}|${edge.edge_type}`,
      edge,
    );
  }

  const upstreamParents = new Map<string, Set<string>>();
  const downstreamChildren = new Map<string, Set<string>>();
  const allNodes = new Set<string>([lineage.entity]);
  for (const edge of uniqueEdges.values()) {
    allNodes.add(edge.from_entity);
    allNodes.add(edge.to_entity);
    let children = downstreamChildren.get(edge.from_entity);
    if (!children) {
      children = new Set<string>();
      downstreamChildren.set(edge.from_entity, children);
    }
    children.add(edge.to_entity);

    let parents = upstreamParents.get(edge.to_entity);
    if (!parents) {
      parents = new Set<string>();
      upstreamParents.set(edge.to_entity, parents);
    }
    parents.add(edge.from_entity);
  }

  const upstreamDepth = walkDepth(lineage.entity, upstreamParents);
  const downstreamDepth = walkDepth(lineage.entity, downstreamChildren);
  const columns = new Map<number, string[]>();
  for (const nodeId of allNodes) {
    let column = 0;
    if (nodeId !== lineage.entity) {
      if (downstreamDepth.has(nodeId)) {
        column = downstreamDepth.get(nodeId) ?? 0;
      } else if (upstreamDepth.has(nodeId)) {
        column = -(upstreamDepth.get(nodeId) ?? 0);
      }
    }
    const bucket = columns.get(column) ?? [];
    bucket.push(nodeId);
    columns.set(column, bucket);
  }

  const nodes: Node[] = [];
  for (const [column, nodeIds] of columns.entries()) {
    const sorted = [...nodeIds].sort((a, b) => a.localeCompare(b));
    const startY = -((sorted.length - 1) * ROW_GAP) / 2;
    for (const [index, nodeId] of sorted.entries()) {
      const isFocal = nodeId === lineage.entity;
      nodes.push({
        id: nodeId,
        type: "default",
        position: {
          x: column * COLUMN_GAP,
          y: startY + index * ROW_GAP,
        },
        data: { label: formatNodeLabel(nodeId, isFocal) },
        style: {
          borderRadius: 10,
          border: isFocal ? "2px solid #0ea5e9" : "1px solid #475569",
          padding: "8px 10px",
          background: isFocal ? "#082f49" : "#0f172a",
          color: "#e2e8f0",
          minWidth: 220,
          maxWidth: 300,
          fontSize: 11,
          fontFamily: "var(--font-mono)",
        },
      });
    }
  }

  const edges: Edge[] = Array.from(uniqueEdges.values()).map((edge) => ({
    id: `${edge.from_entity}->${edge.to_entity}:${edge.edge_type}`,
    source: edge.from_entity,
    target: edge.to_entity,
    label: edge.edge_type.replaceAll("_", " "),
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: "#60a5fa", strokeWidth: 1.6 },
    labelStyle: {
      fill: "#cbd5e1",
      fontSize: 10,
      fontFamily: "var(--font-mono)",
    },
  }));

  return { nodes, edges };
}

function walkDepth(
  root: string,
  adjacency: Map<string, Set<string>>,
): Map<string, number> {
  const depths = new Map<string, number>();
  const queue: Array<{ id: string; depth: number }> = [{ id: root, depth: 0 }];
  const visited = new Set<string>([root]);
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) {
      continue;
    }
    const nextIds = adjacency.get(current.id);
    if (!nextIds) {
      continue;
    }
    for (const nextId of nextIds) {
      if (visited.has(nextId)) {
        continue;
      }
      visited.add(nextId);
      depths.set(nextId, current.depth + 1);
      queue.push({ id: nextId, depth: current.depth + 1 });
    }
  }
  return depths;
}

function formatNodeLabel(urn: string, isFocal: boolean): string {
  const parts = urn.split(":");
  const tail = parts.at(-1) ?? urn;
  const kind = parts.length >= 3 ? parts[2] : "entity";
  const prefix = isFocal ? "focal" : kind;
  return `${prefix}: ${tail}`;
}
