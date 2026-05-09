import type { Edge, Node } from "@xyflow/react";

export type FlowDomain = "agent" | "data" | "strategy" | "bot" | "ml" | "rl";

/**
 * Base shape for AQP flow nodes. Each node carries a `kind` discriminator
 * (palette identity, e.g. `LLM`, `Agent`, `Source`, `Transform`, `Signal`)
 * and a free-form `params` object that the per-domain serializer renders
 * to the backend payload.
 */
export interface AqpNodeData extends Record<string, unknown> {
  kind: string;
  label?: string;
  params?: Record<string, unknown>;
  /** Optional accent override (otherwise resolved via accentByKind). */
  accent?: string;
  /** Free-text annotation surfaced via the right-click context menu. */
  notes?: string;
}

export type AqpNode = Node<AqpNodeData>;
export type AqpEdge = Edge;

/** Plain JSON representation safe to POST or persist server-side. */
export interface FlowGraph {
  domain: FlowDomain;
  version: 1;
  nodes: Array<{
    id: string;
    type?: string;
    position: { x: number; y: number };
    data: AqpNodeData;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    sourceHandle?: string | null;
    targetHandle?: string | null;
    label?: string | null;
  }>;
}

/** Palette tile: how it appears on the left rail and how it spawns. */
export interface PaletteItem {
  kind: string;
  label: string;
  description?: string;
  group?: string;
  defaultParams?: Record<string, unknown>;
  /** Optional accent color for the node card border / header strip. */
  accent?: string;
}

export interface PaletteSection {
  title: string;
  items: PaletteItem[];
}

/**
 * MIME type used by the palette's `dragstart` payload. The canvas
 * registers `dragover` + `drop` handlers that read this type to spawn
 * a node at the cursor position.
 */
export const PALETTE_DRAG_MIME = "application/aqp-flow-node";

export interface PaletteDragPayload {
  kind: string;
  label: string;
  accent?: string;
  defaultParams?: Record<string, unknown>;
}

/** Default accent for a node whose kind is not in `accentByKind`. */
export const DEFAULT_NODE_ACCENT = "#3b82f6";
