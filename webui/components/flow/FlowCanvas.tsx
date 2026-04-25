"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type DefaultEdgeOptions,
  type EdgeTypes,
  type NodeTypes,
  type OnConnect,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, type DragEvent, type ReactNode } from "react";

import { useUiStore } from "@/lib/store/ui";

import { PALETTE_DRAG_MIME } from "./Palette";
import type { AqpEdge, AqpNode, AqpNodeData, FlowDomain, FlowGraph, PaletteItem } from "./types";

interface FlowCanvasProps {
  domain: FlowDomain;
  initialGraph?: FlowGraph;
  nodeTypes: NodeTypes;
  edgeTypes?: EdgeTypes;
  /** Called whenever the graph state changes (debounced is the consumer's job). */
  onGraphChange?: (graph: FlowGraph) => void;
  /** Optional content rendered on top of the canvas (toolbar, etc.). */
  toolbar?: ReactNode;
  defaultEdgeOptions?: DefaultEdgeOptions;
}

const DEFAULT_EDGE_OPTIONS: DefaultEdgeOptions = {
  animated: true,
  style: { stroke: "#3b82f6", strokeWidth: 1.5 },
};

let nextId = 1;
function uniqueId(prefix: string) {
  nextId += 1;
  return `${prefix}-${Date.now().toString(36)}-${nextId}`;
}

function FlowCanvasInner(props: FlowCanvasProps) {
  const {
    domain,
    initialGraph,
    nodeTypes,
    edgeTypes,
    onGraphChange,
    toolbar,
    defaultEdgeOptions = DEFAULT_EDGE_OPTIONS,
  } = props;

  const themeMode = useUiStore((s) => s.themeMode);

  const [nodes, setNodes, onNodesChange] = useNodesState<AqpNode>(
    (initialGraph?.nodes.map((n) => ({
      id: n.id,
      type: n.type ?? "aqp",
      position: n.position,
      data: n.data,
    })) as AqpNode[]) ?? [],
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<AqpEdge>(
    (initialGraph?.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? undefined,
      targetHandle: e.targetHandle ?? undefined,
      label: e.label ?? undefined,
    })) as AqpEdge[]) ?? [],
  );

  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const { screenToFlowPosition } = useReactFlow<AqpNode, AqpEdge>();

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: uniqueId("e"),
            ...defaultEdgeOptions,
          },
          eds,
        ),
      );
    },
    [defaultEdgeOptions, setEdges],
  );

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData(PALETTE_DRAG_MIME);
      if (!raw) return;
      let item: PaletteItem;
      try {
        item = JSON.parse(raw) as PaletteItem;
      } catch {
        return;
      }
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const data: AqpNodeData = {
        kind: item.kind,
        label: item.label,
        params: { ...(item.defaultParams ?? {}) },
      };
      const newNode: AqpNode = {
        id: uniqueId(item.kind.toLowerCase()),
        type: "aqp",
        position,
        data,
      };
      setNodes((nds) => nds.concat(newNode));
    },
    [screenToFlowPosition, setNodes],
  );

  const graph: FlowGraph = useMemo(
    () => ({
      domain,
      version: 1,
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: n.data,
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle ?? null,
        targetHandle: e.targetHandle ?? null,
        label: typeof e.label === "string" ? e.label : null,
      })),
    }),
    [domain, nodes, edges],
  );

  useEffect(() => {
    onGraphChange?.(graph);
  }, [graph, onGraphChange]);

  return (
    <div ref={wrapperRef} style={{ width: "100%", height: "100%", position: "relative" }}>
      {toolbar ? (
        <div
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            zIndex: 5,
            display: "flex",
            gap: 8,
          }}
        >
          {toolbar}
        </div>
      ) : null}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        snapToGrid
        snapGrid={[16, 16]}
        fitView
        proOptions={{ hideAttribution: true }}
        colorMode={themeMode === "dark" ? "dark" : "light"}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
        <Controls position="bottom-right" showInteractive={false} />
        <MiniMap pannable zoomable position="bottom-left" />
      </ReactFlow>
    </div>
  );
}

export function FlowCanvas(props: FlowCanvasProps) {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
