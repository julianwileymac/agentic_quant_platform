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
  type NodeMouseHandler,
  type NodeTypes,
  type OnConnect,
} from "@xyflow/react";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  type DragEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";

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
  onNodeClick?: (node: AqpNode) => void;
  onNodeContextMenu?: (
    node: AqpNode,
    position: { x: number; y: number },
  ) => void;
  onPaneContextMenu?: (position: { x: number; y: number }) => void;
}

export interface FlowCanvasHandle {
  addPaletteNodeAtPoint: (item: PaletteItem, screenX: number, screenY: number) => void;
  duplicateNode: (nodeId: string) => void;
  removeNode: (nodeId: string) => void;
  disconnectNode: (nodeId: string) => void;
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

const FlowCanvasInner = forwardRef<FlowCanvasHandle, FlowCanvasProps>(function FlowCanvasInner(
  props,
  ref,
) {
  const {
    domain,
    initialGraph,
    nodeTypes,
    edgeTypes,
    onGraphChange,
    toolbar,
    defaultEdgeOptions = DEFAULT_EDGE_OPTIONS,
    onNodeClick,
    onNodeContextMenu,
    onPaneContextMenu,
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

  useImperativeHandle(
    ref,
    () => ({
      addPaletteNodeAtPoint: (item, screenX, screenY) => {
        const position = screenToFlowPosition({ x: screenX, y: screenY });
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
      duplicateNode: (nodeId) => {
        setNodes((nds) => {
          const found = nds.find((n) => n.id === nodeId);
          if (!found) return nds;
          const clone: AqpNode = {
            ...found,
            id: uniqueId(`${found.data.kind ?? "node"}-copy`),
            position: { x: found.position.x + 32, y: found.position.y + 32 },
            data: {
              ...found.data,
              label: `${found.data.label ?? found.data.kind ?? "node"} (copy)`,
            },
          };
          return nds.concat(clone);
        });
      },
      removeNode: (nodeId) => {
        setNodes((nds) => nds.filter((n) => n.id !== nodeId));
        setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      },
      disconnectNode: (nodeId) => {
        setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      },
    }),
    [screenToFlowPosition, setEdges, setNodes],
  );

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_evt, node) => {
      onNodeClick?.(node as AqpNode);
    },
    [onNodeClick],
  );

  const handleNodeContextMenu: NodeMouseHandler = useCallback(
    (evt, node) => {
      evt.preventDefault();
      onNodeContextMenu?.(node as AqpNode, { x: evt.clientX, y: evt.clientY });
    },
    [onNodeContextMenu],
  );

  const handlePaneContextMenu = useCallback(
    (evt: ReactMouseEvent | MouseEvent) => {
      evt.preventDefault();
      onPaneContextMenu?.({
        x: (evt as MouseEvent).clientX,
        y: (evt as MouseEvent).clientY,
      });
    },
    [onPaneContextMenu],
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
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeClick}
        onNodeContextMenu={handleNodeContextMenu}
        onPaneContextMenu={handlePaneContextMenu}
        deleteKeyCode={["Backspace", "Delete"]}
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
});

export const FlowCanvas = forwardRef<FlowCanvasHandle, FlowCanvasProps>(function FlowCanvas(
  props,
  ref,
) {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner {...props} ref={ref} />
    </ReactFlowProvider>
  );
});
