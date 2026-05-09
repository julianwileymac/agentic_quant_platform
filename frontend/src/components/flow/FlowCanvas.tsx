import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type Connection,
  type DefaultEdgeOptions,
  type Edge,
  type NodeProps,
  type NodeTypes,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
  type ReactFlowInstance,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
} from "@xyflow/react";
import {
  forwardRef,
  type DragEvent,
  type ReactElement,
  useCallback,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";

import "@xyflow/react/dist/style.css";

import { AqpNodeCard } from "./AqpNodeCard";
import {
  DEFAULT_NODE_ACCENT,
  PALETTE_DRAG_MIME,
  type AqpNode,
  type FlowGraph,
  type PaletteDragPayload,
} from "./types";

export interface FlowCanvasHandle {
  fitView: () => void;
  focusNode: (id: string) => void;
  getInstance: () => ReactFlowInstance | null;
}

interface FlowCanvasProps {
  /** Controlled nodes; updates flow upward via `onNodesChange`. */
  nodes: AqpNode[];
  /** Controlled edges. */
  edges: Edge[];
  onNodesChange: (nodes: AqpNode[]) => void;
  onEdgesChange: (edges: Edge[]) => void;
  /** Called when the user releases a palette tile on the canvas. */
  onPaletteDrop?: (payload: PaletteDragPayload, position: { x: number; y: number }) => void;
  /** Click on a node — used by WorkflowEditor to open the params drawer. */
  onNodeClick?: (node: AqpNode) => void;
  /** Right-click on a node — used to open the context menu. */
  onNodeContextMenu?: (node: AqpNode, event: { clientX: number; clientY: number }) => void;
  accentByKind?: Record<string, string>;
  className?: string;
}

const defaultEdgeOptions: DefaultEdgeOptions = {
  animated: true,
  markerEnd: { type: MarkerType.ArrowClosed },
};

/**
 * Controlled React Flow canvas. WorkflowEditor owns node / edge state
 * and feeds it down; this component handles the rendering, the
 * drop-target wiring, and exposes an imperative handle for fitView /
 * focusNode.
 */
export const FlowCanvas = forwardRef<FlowCanvasHandle, FlowCanvasProps>(function FlowCanvasImpl(
  props,
  ref,
) {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner {...props} canvasRef={ref} />
    </ReactFlowProvider>
  );
});

interface FlowCanvasInnerProps extends FlowCanvasProps {
  canvasRef: React.ForwardedRef<FlowCanvasHandle>;
}

function FlowCanvasInner({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onPaletteDrop,
  onNodeClick,
  onNodeContextMenu,
  accentByKind,
  className,
  canvasRef,
}: FlowCanvasInnerProps) {
  const instance = useReactFlow();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [_isDragOver, setDragOver] = useState(false);

  useImperativeHandle(
    canvasRef,
    () => ({
      fitView: () => instance.fitView({ padding: 0.2 }),
      focusNode: (id: string) => {
        const target = instance.getNode(id);
        if (!target) return;
        instance.setCenter(
          target.position.x + ((target.width as number | undefined) ?? 220) / 2,
          target.position.y + ((target.height as number | undefined) ?? 80) / 2,
          { duration: 250, zoom: 1 },
        );
      },
      getInstance: () => instance,
    }),
    [instance],
  );

  const handleNodesChange: OnNodesChange<AqpNode> = useCallback(
    (changes) => {
      const next = applyNodeChanges<AqpNode>(changes, nodes);
      onNodesChange(next);
    },
    [nodes, onNodesChange],
  );
  const handleEdgesChange: OnEdgesChange = useCallback(
    (changes) => onEdgesChange(applyEdgeChanges(changes, edges)),
    [edges, onEdgesChange],
  );
  const handleConnect: OnConnect = useCallback(
    (params: Connection) => {
      onEdgesChange(
        addEdge(
          {
            ...params,
            animated: true,
            markerEnd: { type: MarkerType.ArrowClosed },
          },
          edges,
        ),
      );
    },
    [edges, onEdgesChange],
  );

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    if (Array.from(e.dataTransfer.types).includes(PALETTE_DRAG_MIME)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setDragOver(true);
    }
  }, []);
  const handleDragLeave = useCallback(() => setDragOver(false), []);
  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      setDragOver(false);
      const raw = e.dataTransfer.getData(PALETTE_DRAG_MIME);
      if (!raw) return;
      e.preventDefault();
      try {
        const payload = JSON.parse(raw) as PaletteDragPayload;
        const position = instance.screenToFlowPosition({ x: e.clientX, y: e.clientY });
        onPaletteDrop?.(payload, position);
      } catch {
        // Ignore malformed payloads.
      }
    },
    [instance, onPaletteDrop],
  );

  const nodeTypes: NodeTypes = useMemo(
    () => ({
      aqp: ((props: NodeProps<AqpNode>) => (
        <AqpNodeCard
          {...props}
          accent={accentByKind?.[props.data.kind] ?? props.data.accent ?? DEFAULT_NODE_ACCENT}
        />
      )) as unknown as NodeTypes["aqp"],
    }),
    [accentByKind],
  );

  return (
    <div
      ref={wrapperRef}
      className={className}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{ width: "100%", height: "100%" }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        onNodeClick={(_event, node) => onNodeClick?.(node as AqpNode)}
        onNodeContextMenu={(event, node) => {
          event.preventDefault();
          onNodeContextMenu?.(node as AqpNode, { clientX: event.clientX, clientY: event.clientY });
        }}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#1F2937" />
        <Controls />
        <MiniMap pannable zoomable nodeColor={() => "#3B82F6"} maskColor="rgba(15, 23, 42, 0.8)" />
      </ReactFlow>
    </div>
  );
}

/**
 * Rebuild a `FlowGraph` from React Flow's controlled `nodes` + `edges`
 * arrays. Used by WorkflowEditor whenever the user clicks "Save".
 */
export function toFlowGraph(domain: FlowGraph["domain"], nodes: AqpNode[], edges: Edge[]): FlowGraph {
  return {
    domain,
    version: 1,
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type ?? "aqp",
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
  };
}

/**
 * Inverse: hydrate React Flow `nodes` + `edges` from a saved
 * `FlowGraph`. Sets `type: "aqp"` so the custom node renderer kicks in.
 */
export function fromFlowGraph(graph: FlowGraph): { nodes: AqpNode[]; edges: Edge[] } {
  const nodes: AqpNode[] = graph.nodes.map((n) => ({
    id: n.id,
    type: n.type ?? "aqp",
    position: n.position,
    data: n.data,
  })) as AqpNode[];
  const edges: Edge[] = graph.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    ...(e.sourceHandle != null ? { sourceHandle: e.sourceHandle } : {}),
    ...(e.targetHandle != null ? { targetHandle: e.targetHandle } : {}),
    ...(e.label != null ? { label: e.label } : {}),
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));
  return { nodes, edges };
}

/**
 * Workflows-agent route already imports a no-prop `<FlowCanvas/>` for
 * its preview seed. Re-export the underlying `FlowCanvasInner` as
 * `LegacyPreviewCanvas` in case any older callsite still relies on
 * the seed-only entry. Returns a `ReactElement` for type clarity.
 */
export type { ReactElement };
