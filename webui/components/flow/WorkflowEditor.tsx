"use client";

import { ExportOutlined, ImportOutlined, SaveOutlined } from "@ant-design/icons";
import { App, Button, Card, Drawer, Form, Input, Space, Tag, Tooltip } from "antd";
import { useCallback, useMemo, useRef, useState } from "react";

import type { NodeProps, NodeTypes } from "@xyflow/react";

import { AqpNodeCard } from "./AqpNodeCard";
import { CanvasContextMenu } from "./CanvasContextMenu";
import { FlowCanvas, type FlowCanvasHandle } from "./FlowCanvas";
import { Palette } from "./Palette";
import type {
  AqpNode,
  AqpNodeData,
  FlowDomain,
  FlowGraph,
  PaletteSection,
} from "./types";

export interface WorkflowEditorProps {
  domain: FlowDomain;
  paletteSections: PaletteSection[];
  initialGraph?: FlowGraph;
  onRun?: (graph: FlowGraph) => Promise<void> | void;
  /** Optional accent overrides for known kinds. */
  accentByKind?: Record<string, string>;
  toolbarExtras?: React.ReactNode;
}

interface ContextMenuState {
  open: boolean;
  position: { x: number; y: number } | null;
  nodeId: string | null;
}

export function WorkflowEditor(props: WorkflowEditorProps) {
  const {
    domain,
    paletteSections,
    initialGraph,
    onRun,
    accentByKind,
    toolbarExtras,
  } = props;
  const { message } = App.useApp();
  const [graph, setGraph] = useState<FlowGraph>(
    initialGraph ?? { domain, version: 1, nodes: [], edges: [] },
  );
  const [drawerNode, setDrawerNode] = useState<AqpNode | null>(null);
  const [menu, setMenu] = useState<ContextMenuState>({
    open: false,
    position: null,
    nodeId: null,
  });
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const canvasRef = useRef<FlowCanvasHandle | null>(null);

  const nodeTypes: NodeTypes = useMemo(() => {
    return {
      aqp: (np: NodeProps<AqpNode>) => (
        <AqpNodeCard {...np} accent={accentByKind?.[np.data.kind] ?? "#3b82f6"} />
      ),
    };
  }, [accentByKind]);

  const onGraphChange = useCallback((g: FlowGraph) => {
    setGraph(g);
  }, []);

  function exportJson() {
    const text = JSON.stringify(graph, null, 2);
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${domain}-flow.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function importJson() {
    fileInputRef.current?.click();
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as FlowGraph;
      if (parsed.domain !== domain) {
        message.warning(`Loaded graph has domain "${parsed.domain}", expected "${domain}"`);
      }
      setGraph(parsed);
      message.success("Graph loaded");
    } catch (err) {
      message.error(`Could not load graph: ${(err as Error).message}`);
    }
  }

  async function run() {
    if (!onRun) return;
    try {
      await onRun(graph);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  function closeMenu() {
    setMenu({ open: false, position: null, nodeId: null });
  }

  return (
    <div style={{ display: "flex", height: "calc(100vh - 100px)", overflow: "hidden", borderRadius: 8 }}>
      <Palette sections={paletteSections} />
      <div style={{ flex: 1, position: "relative" }}>
        <FlowCanvas
          ref={canvasRef}
          domain={domain}
          initialGraph={graph}
          nodeTypes={nodeTypes}
          onGraphChange={onGraphChange}
          onNodeClick={(node) => setDrawerNode(node)}
          onNodeContextMenu={(node, position) =>
            setMenu({ open: true, position, nodeId: node.id })
          }
          onPaneContextMenu={(position) =>
            setMenu({ open: true, position, nodeId: null })
          }
          toolbar={
            <Space>
              {toolbarExtras}
              <Tooltip title="Import JSON">
                <Button icon={<ImportOutlined />} onClick={importJson} />
              </Tooltip>
              <Tooltip title="Export JSON">
                <Button icon={<ExportOutlined />} onClick={exportJson} />
              </Tooltip>
              {onRun ? (
                <Button type="primary" icon={<SaveOutlined />} onClick={run}>
                  Run
                </Button>
              ) : null}
            </Space>
          }
        />
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          style={{ display: "none" }}
          onChange={onFile}
        />
      </div>
      <Drawer
        open={Boolean(drawerNode)}
        onClose={() => setDrawerNode(null)}
        title={drawerNode ? `${drawerNode.data.kind} — ${drawerNode.data.label ?? drawerNode.id}` : ""}
        width={360}
      >
        {drawerNode ? <NodeEditor node={drawerNode} onChange={(d) => updateNode(drawerNode.id, d)} /> : null}
      </Drawer>
      <CanvasContextMenu
        open={menu.open}
        position={menu.position}
        nodeId={menu.nodeId}
        paletteSections={paletteSections}
        onClose={closeMenu}
        onAddNode={(item) => {
          if (!menu.position || !canvasRef.current) return;
          canvasRef.current.addPaletteNodeAtPoint(item, menu.position.x, menu.position.y);
        }}
        onDuplicateNode={(id) => canvasRef.current?.duplicateNode(id)}
        onDeleteNode={(id) => canvasRef.current?.removeNode(id)}
        onDisconnectNode={(id) => canvasRef.current?.disconnectNode(id)}
      />
    </div>
  );

  function updateNode(id: string, data: AqpNodeData) {
    setGraph((g) => ({
      ...g,
      nodes: g.nodes.map((n) => (n.id === id ? { ...n, data } : n)),
    }));
    setDrawerNode((current) =>
      current && current.id === id
        ? { ...current, data }
        : current,
    );
  }
}

function NodeEditor({
  node,
  onChange,
}: {
  node: AqpNode;
  onChange: (data: AqpNodeData) => void;
}) {
  const params = node.data.params ?? {};
  return (
    <Card size="small" title={<Tag>{node.data.kind}</Tag>}>
      <Form layout="vertical">
        <Form.Item label="Label">
          <Input
            value={node.data.label ?? ""}
            onChange={(e) => onChange({ ...node.data, label: e.target.value })}
          />
        </Form.Item>
        <Form.Item label="Notes">
          <Input.TextArea
            value={node.data.notes ?? ""}
            onChange={(e) => onChange({ ...node.data, notes: e.target.value })}
            autoSize
          />
        </Form.Item>
        <Form.Item label="Params (JSON)">
          <Input.TextArea
            value={JSON.stringify(params, null, 2)}
            autoSize={{ minRows: 4, maxRows: 16 }}
            onChange={(e) => {
              try {
                const next = JSON.parse(e.target.value) as Record<string, unknown>;
                onChange({ ...node.data, params: next });
              } catch {
                /* ignore until JSON is valid */
              }
            }}
          />
        </Form.Item>
      </Form>
    </Card>
  );
}
