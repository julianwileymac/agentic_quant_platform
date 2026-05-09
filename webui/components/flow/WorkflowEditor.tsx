"use client";

import { ExportOutlined, ImportOutlined, SaveOutlined } from "@ant-design/icons";
import { App, Button, Card, Drawer, Form, Input, InputNumber, Select, Space, Tag, Tooltip } from "antd";
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
  paletteSections?: PaletteSection[];
  /** Backwards-compatible alias for older builder pages. */
  palette?: PaletteSection[];
  initialGraph?: FlowGraph;
  /** Controlled-graph aliases used by older builder pages. */
  value?: FlowGraph;
  onChange?: (graph: FlowGraph) => void;
  onRun?: (graph: FlowGraph) => Promise<void> | void;
  /** Optional accent overrides for known kinds. */
  accentByKind?: Record<string, string>;
  toolbarExtras?: React.ReactNode;
  height?: string | number;
}

interface ContextMenuState {
  open: boolean;
  position: { x: number; y: number } | null;
  nodeId: string | null;
}

export function WorkflowEditor(props: WorkflowEditorProps) {
  const {
    domain,
    paletteSections: paletteSectionsProp,
    palette,
    initialGraph: initialGraphProp,
    value,
    onChange,
    onRun,
    accentByKind,
    toolbarExtras,
    height = "calc(100vh - 100px)",
  } = props;
  const paletteSections = paletteSectionsProp ?? palette ?? [];
  const initialGraph = value ?? initialGraphProp;
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
    onChange?.(g);
  }, [onChange]);

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
    <div style={{ display: "flex", height, overflow: "hidden", borderRadius: 8 }}>
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
  const updateParams = (patch: Record<string, unknown>) =>
    onChange({ ...node.data, params: { ...params, ...patch } });

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
        {node.data.kind === "Source" ? (
          <Card size="small" title="Fetch slice" style={{ marginBottom: 12 }}>
            <Form.Item label="Provider">
              <Select
                value={String(params.provider ?? "yahoo")}
                onChange={(provider) => updateParams({ provider })}
                options={[
                  { value: "yahoo", label: "Yahoo / yfinance" },
                  { value: "alpha_vantage", label: "Alpha Vantage" },
                  { value: "ibkr", label: "IBKR" },
                  { value: "alpaca", label: "Alpaca" },
                  { value: "fred", label: "FRED" },
                ]}
              />
            </Form.Item>
            <Form.Item label="Symbol mode">
              <Select
                value={String(params.symbol_mode ?? "explicit")}
                onChange={(symbol_mode) => updateParams({ symbol_mode })}
                options={[
                  { value: "explicit", label: "Explicit symbols" },
                  { value: "all_active", label: "All active" },
                  { value: "query", label: "Query" },
                  { value: "universe", label: "Universe" },
                ]}
              />
            </Form.Item>
            <Form.Item label="Symbols">
              <Select
                mode="tags"
                tokenSeparators={[",", " "]}
                value={Array.isArray(params.symbols) ? params.symbols.map(String) : parseTags(params.symbols)}
                onChange={(symbols) => updateParams({ symbols })}
                placeholder="SPY, AAPL, MSFT"
              />
            </Form.Item>
            <Form.Item label="Universe query">
              <Input
                value={String(params.query ?? "")}
                onChange={(e) => updateParams({ query: e.target.value })}
              />
            </Form.Item>
            <Space.Compact style={{ width: "100%" }}>
              <Form.Item label="Start" style={{ width: "50%" }}>
                <Input
                  type="date"
                  value={String(params.start ?? "")}
                  onChange={(e) => updateParams({ start: e.target.value })}
                />
              </Form.Item>
              <Form.Item label="End" style={{ width: "50%" }}>
                <Input
                  type="date"
                  value={String(params.end ?? "")}
                  onChange={(e) => updateParams({ end: e.target.value })}
                />
              </Form.Item>
            </Space.Compact>
            <Form.Item label="Interval / timeframe">
              <Select
                value={String(params.interval ?? "1d")}
                onChange={(interval) => updateParams({ interval, timeframe: interval })}
                options={["1min", "5min", "15min", "30min", "60min", "1d", "1wk", "1mo"].map(
                  (value) => ({ value, label: value }),
                )}
              />
            </Form.Item>
            <Space.Compact style={{ width: "100%" }}>
              <Form.Item label="Limit" style={{ width: "50%" }}>
                <InputNumber
                  min={1}
                  style={{ width: "100%" }}
                  value={typeof params.limit === "number" ? params.limit : undefined}
                  onChange={(limit) => updateParams({ limit })}
                />
              </Form.Item>
              <Form.Item label="Offset" style={{ width: "50%" }}>
                <InputNumber
                  min={0}
                  style={{ width: "100%" }}
                  value={typeof params.offset === "number" ? params.offset : 0}
                  onChange={(offset) => updateParams({ offset })}
                />
              </Form.Item>
            </Space.Compact>
            <Form.Item label="Partition kind">
              <Select
                value={String(params.partition_kind ?? "none")}
                onChange={(partition_kind) => updateParams({ partition_kind })}
                options={["none", "daily", "weekly", "monthly", "symbol", "static"].map((value) => ({
                  value,
                  label: value,
                }))}
              />
            </Form.Item>
            <Form.Item label="Provider options (JSON)">
              <Input.TextArea
                value={JSON.stringify(params.provider_options ?? {}, null, 2)}
                autoSize={{ minRows: 2, maxRows: 8 }}
                onChange={(e) => {
                  try {
                    updateParams({ provider_options: JSON.parse(e.target.value || "{}") });
                  } catch {
                    /* ignore until JSON is valid */
                  }
                }}
              />
            </Form.Item>
          </Card>
        ) : null}
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

function parseTags(value: unknown): string[] {
  if (typeof value !== "string") return [];
  return value
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}
