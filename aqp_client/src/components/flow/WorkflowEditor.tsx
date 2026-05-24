import type { Edge } from "@xyflow/react";
import { Download, FlaskConical, Maximize2, RotateCcw, Save, Upload } from "lucide-react";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";

import { CanvasContextMenu } from "./CanvasContextMenu";
import { FlowCanvas, fromFlowGraph, toFlowGraph, type FlowCanvasHandle } from "./FlowCanvas";
import { NodeParamsDrawer } from "./NodeParamsDrawer";
import { Palette } from "./Palette";
import {
  type AqpNode,
  type FlowDomain,
  type FlowGraph,
  type PaletteDragPayload,
  type PaletteSection,
} from "./types";

interface WorkflowEditorProps {
  domain: FlowDomain;
  paletteSections: PaletteSection[];
  accentByKind?: Record<string, string>;
  initialGraph?: FlowGraph;
  /** Called when the user clicks Save. Errors propagate via toast. */
  onSave?: (graph: FlowGraph) => Promise<void> | void;
  /** Optional Run quick action (e.g. start a backtest from the spec). */
  onRun?: (graph: FlowGraph) => Promise<void> | void;
  /**
   * Optional callback fired whenever the canvas selection changes.
   * The Data Lab Testing route uses this to mount the RJSF typed
   * inspector in the shell's right rail without replacing the
   * built-in JSON drawer (so other domains keep working).
   */
  onNodeSelected?: (node: AqpNode | null) => void;
  /**
   * Optional callback fired whenever the canvas graph changes
   * (nodes / edges added, moved, deleted, or params edited via
   * the built-in drawer). Used by the Data Lab to mirror node
   * updates back to the LabGraph store + the right-rail inspector
   * so the inspector reflects the latest params after a drawer
   * save.
   */
  onGraphChange?: (graph: FlowGraph) => void;
  /** Optional toolbar buttons rendered next to Save / Run. */
  toolbarExtras?: ReactNode;
  /** Disable Save / Run buttons. */
  saving?: boolean;
}

/**
 * Domain-agnostic visual editor used by every Phase 4 surface (Bot
 * Builder, Strategy Composer, Data Pipeline, ML Builder, RL Lab,
 * Agent Crew). Composes Palette + FlowCanvas + NodeParamsDrawer +
 * CanvasContextMenu and exposes Save / Run callbacks that operate on
 * a serialised `FlowGraph`.
 */
export function WorkflowEditor({
  domain,
  paletteSections,
  accentByKind,
  initialGraph,
  onSave,
  onRun,
  onNodeSelected,
  onGraphChange,
  toolbarExtras,
  saving = false,
}: WorkflowEditorProps) {
  const initialHydrated = useMemo(
    () => (initialGraph ? fromFlowGraph(initialGraph) : { nodes: [], edges: [] }),
    [initialGraph],
  );
  const [nodes, setNodes] = useState<AqpNode[]>(initialHydrated.nodes);
  const [edges, setEdges] = useState<Edge[]>(initialHydrated.edges);
  const [drawerNode, setDrawerNode] = useState<AqpNode | null>(null);
  const [selectedPaletteItem, setSelectedPaletteItem] = useState<PaletteDragPayload | null>(null);
  const [menu, setMenu] = useState<{
    open: boolean;
    position: { x: number; y: number } | null;
    nodeId: string | null;
  }>({ open: false, position: null, nodeId: null });
  const canvasRef = useRef<FlowCanvasHandle | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const idSeq = useRef(initialHydrated.nodes.length);

  // Re-hydrate on initialGraph swap (e.g. when loading a different bot id).
  useEffect(() => {
    if (!initialGraph) return;
    const hydrated = fromFlowGraph(initialGraph);
    setNodes(hydrated.nodes);
    setEdges(hydrated.edges);
    idSeq.current = hydrated.nodes.length;
  }, [initialGraph]);

  // Notify parent on any graph change (nodes / edges) so Lab can
  // mirror the canvas state back to the LabGraph store.
  useEffect(() => {
    if (!onGraphChange) return;
    onGraphChange(toFlowGraph(domain, nodes, edges));
  }, [onGraphChange, domain, nodes, edges]);

  const handlePaletteDrop = useCallback(
    (payload: PaletteDragPayload, position: { x: number; y: number }) => {
      idSeq.current += 1;
      const id = `n-${Date.now()}-${idSeq.current}`;
      const newNode: AqpNode = {
        id,
        type: "aqp",
        position,
        data: {
          kind: payload.kind,
          label: payload.label,
          params: payload.defaultParams ? structuredClone(payload.defaultParams) : {},
          ...(payload.accent !== undefined ? { accent: payload.accent } : {}),
        },
      };
      setNodes((prev) => [...prev, newNode]);
    },
    [],
  );

  const addPaletteNode = useCallback(
    (payload: PaletteDragPayload, position?: { x: number; y: number }) => {
      const targetPosition = position ?? canvasRef.current?.getViewportCenter() ?? { x: 0, y: 0 };
      handlePaletteDrop(payload, targetPosition);
    },
    [handlePaletteDrop],
  );

  const updateNode = useCallback(
    (id: string, updater: (node: AqpNode) => AqpNode) => {
      setNodes((prev) => prev.map((n) => (n.id === id ? updater(n) : n)));
    },
    [],
  );

  const deleteNode = useCallback((id: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== id));
    setEdges((prev) => prev.filter((e) => e.source !== id && e.target !== id));
  }, []);

  const duplicateNode = useCallback(
    (id: string) => {
      setNodes((prev) => {
        const target = prev.find((n) => n.id === id);
        if (!target) return prev;
        idSeq.current += 1;
        const copy: AqpNode = {
          ...target,
          id: `n-${Date.now()}-${idSeq.current}`,
          position: { x: target.position.x + 40, y: target.position.y + 40 },
          data: { ...target.data, params: { ...(target.data.params ?? {}) } },
        };
        return [...prev, copy];
      });
    },
    [],
  );

  const exportGraph = useCallback(async () => {
    const graph = toFlowGraph(domain, nodes, edges);
    const text = JSON.stringify(graph, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Graph copied to clipboard");
    } catch {
      // Fallback: download as a JSON file.
      const blob = new Blob([text], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${domain}-graph.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.info("Graph downloaded");
    }
  }, [domain, nodes, edges]);

  const importGraph = useCallback(async (file: File) => {
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as FlowGraph;
      if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.nodes)) {
        throw new Error("Not a valid AQP flow graph");
      }
      const hydrated = fromFlowGraph(parsed);
      setNodes(hydrated.nodes);
      setEdges(hydrated.edges);
      idSeq.current = hydrated.nodes.length;
      toast.success(`Imported ${hydrated.nodes.length} nodes`);
    } catch (err) {
      toast.error(`Import failed: ${(err as Error).message}`);
    }
  }, []);

  const handleSave = useCallback(async () => {
    if (!onSave) return;
    const graph = toFlowGraph(domain, nodes, edges);
    try {
      await onSave(graph);
    } catch (err) {
      toast.error(`Save failed: ${(err as Error).message}`);
    }
  }, [onSave, domain, nodes, edges]);

  const handleRun = useCallback(async () => {
    if (!onRun) return;
    const graph = toFlowGraph(domain, nodes, edges);
    try {
      await onRun(graph);
    } catch (err) {
      toast.error(`Run failed: ${(err as Error).message}`);
    }
  }, [onRun, domain, nodes, edges]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-2 py-2">
          <Button variant="ghost" size="sm" onClick={() => canvasRef.current?.fitView()} className="gap-2">
            <Maximize2 className="h-4 w-4" /> Fit view
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setNodes([]);
              setEdges([]);
            }}
            className="gap-2"
          >
            <RotateCcw className="h-4 w-4" /> Clear
          </Button>
          <Button variant="ghost" size="sm" onClick={exportGraph} className="gap-2">
            <Download className="h-4 w-4" /> Export
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            className="gap-2"
          >
            <Upload className="h-4 w-4" /> Import
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importGraph(file);
              e.target.value = "";
            }}
          />
          <div className="flex-1" />
          {toolbarExtras}
          {onRun ? (
            <Button variant="warn" size="sm" onClick={handleRun} disabled={saving} className="gap-2">
              <FlaskConical className="h-4 w-4" /> Run
            </Button>
          ) : null}
          {onSave ? (
            <Button size="sm" onClick={handleSave} disabled={saving} className="gap-2">
              <Save className="h-4 w-4" /> {saving ? "Saving…" : "Save"}
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <div className="flex min-h-0 flex-1 gap-2">
        <Palette
          sections={paletteSections}
          selectedKind={selectedPaletteItem?.kind ?? null}
          onItemClick={(item) => {
            setSelectedPaletteItem(item);
            addPaletteNode(item);
          }}
        />
        <Card className="flex min-h-0 flex-1 overflow-hidden">
          <CardContent className="h-full min-h-0 w-full min-w-0 flex-1 p-0">
            <FlowCanvas
              ref={canvasRef}
              nodes={nodes}
              edges={edges}
              onNodesChange={setNodes}
              onEdgesChange={setEdges}
              onPaletteDrop={handlePaletteDrop}
              onNodeClick={(node) => {
                setSelectedPaletteItem(null);
                setDrawerNode(node);
                onNodeSelected?.(node);
              }}
              onNodeContextMenu={(node, pos) =>
                setMenu({ open: true, position: { x: pos.clientX, y: pos.clientY }, nodeId: node.id })
              }
              {...(accentByKind ? { accentByKind } : {})}
            />
          </CardContent>
        </Card>
      </div>

      <NodeParamsDrawer
        node={drawerNode}
        onClose={() => setDrawerNode(null)}
        onSave={(next) => {
          if (!drawerNode) return;
          updateNode(drawerNode.id, (n) => ({
            ...n,
            data: {
              ...n.data,
              label: next.label,
              params: next.params,
              ...(next.notes ? { notes: next.notes } : {}),
            },
          }));
        }}
      />

      <CanvasContextMenu
        open={menu.open}
        position={menu.position}
        nodeId={menu.nodeId}
        onClose={() => setMenu({ open: false, position: null, nodeId: null })}
        onEdit={() => {
          const target = nodes.find((n) => n.id === menu.nodeId);
          if (target) setDrawerNode(target);
          setMenu({ open: false, position: null, nodeId: null });
        }}
        onDuplicate={() => {
          if (menu.nodeId) duplicateNode(menu.nodeId);
          setMenu({ open: false, position: null, nodeId: null });
        }}
        onDelete={() => {
          if (menu.nodeId) deleteNode(menu.nodeId);
          setMenu({ open: false, position: null, nodeId: null });
        }}
        onFocus={() => {
          if (menu.nodeId) canvasRef.current?.focusNode(menu.nodeId);
          setMenu({ open: false, position: null, nodeId: null });
        }}
        onAddNote={() => {
          if (menu.nodeId) {
            const text = window.prompt("Add a note for this node");
            if (text != null) {
              updateNode(menu.nodeId, (n) => ({ ...n, data: { ...n.data, notes: text } }));
            }
          }
          setMenu({ open: false, position: null, nodeId: null });
        }}
      />
    </div>
  );
}

export { fromFlowGraph, toFlowGraph } from "./FlowCanvas";
