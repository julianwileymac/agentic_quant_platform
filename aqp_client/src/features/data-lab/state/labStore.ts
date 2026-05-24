import { create } from "zustand";

import type {
  LabGraphOut,
  LabGraphSpec,
  LabMode,
  LabNodeStatus,
  LabRunOut,
} from "@/lib/api/lab";

import type { LabServerEnvelope } from "../ws/envelopes";

interface NodeRuntimeState {
  status: LabNodeStatus | "pending";
  lastMetricAt?: number;
  lastError?: string | null;
  metrics?: Record<string, unknown>;
}

interface LabSessionState {
  /** Active Lab id (workspace.lab) the page is currently scoped to. */
  labId: string | null;
  /** Lab mode currently displayed by the LabShell. */
  mode: LabMode;
  /** Per-session id used for the multiplexed /ws/lab/{session_id} channel. */
  sessionId: string;
  /** The graph the user is currently editing in the canvas. */
  draftGraph: LabGraphOut | null;
  /** The most-recently-submitted run (gold-tile state). */
  currentRun: LabRunOut | null;
  /** Per-node runtime status driven by Lab WS envelopes. */
  nodeStatus: Record<string, NodeRuntimeState>;
  /** Bounded ring of the last 200 envelopes for the RunHistory drawer. */
  recentEnvelopes: LabServerEnvelope[];
  /** Whether the right-rail inspector is open. */
  inspectorOpen: boolean;
  /** Selected node id (drives the inspector). */
  selectedNodeId: string | null;
  /**
   * Most-recent uncommitted GraphSpec edit from the Testing canvas.
   * The Testing route mirrors every ``onGraphChange`` event into
   * this field so the LabShell's right-rail inspector can render
   * the latest params without re-fetching the persisted row.
   */
  liveSpec: LabGraphSpec | null;
}

interface LabSessionActions {
  setLabId: (labId: string | null) => void;
  setMode: (mode: LabMode) => void;
  setDraftGraph: (graph: LabGraphOut | null) => void;
  setCurrentRun: (run: LabRunOut | null) => void;
  setSelectedNode: (nodeId: string | null) => void;
  setLiveSpec: (spec: LabGraphSpec | null) => void;
  toggleInspector: (open?: boolean) => void;
  pushEnvelope: (env: LabServerEnvelope) => void;
  resetSession: () => void;
}

export type LabSessionStore = LabSessionState & LabSessionActions;

const ENVELOPE_RING_CAP = 200;

function freshSessionId(): string {
  return `lab-${Math.random().toString(36).slice(2, 12)}`;
}

export const useLabStore = create<LabSessionStore>((set) => ({
  labId: null,
  mode: "testing",
  sessionId: freshSessionId(),
  draftGraph: null,
  currentRun: null,
  nodeStatus: {},
  recentEnvelopes: [],
  inspectorOpen: false,
  selectedNodeId: null,
  liveSpec: null,

  setLabId: (labId) => set({ labId }),
  setMode: (mode) => set({ mode }),
  setDraftGraph: (draftGraph) =>
    set({
      draftGraph,
      nodeStatus: {},
      currentRun: null,
      selectedNodeId: null,
      liveSpec: null,
    }),
  setCurrentRun: (currentRun) => set({ currentRun }),
  setSelectedNode: (selectedNodeId) =>
    set((s) => ({
      selectedNodeId,
      inspectorOpen: selectedNodeId != null || s.inspectorOpen,
    })),
  setLiveSpec: (liveSpec) => set({ liveSpec }),
  toggleInspector: (open) =>
    set((s) => ({ inspectorOpen: open ?? !s.inspectorOpen })),
  resetSession: () =>
    set({
      labId: null,
      sessionId: freshSessionId(),
      draftGraph: null,
      currentRun: null,
      nodeStatus: {},
      recentEnvelopes: [],
      selectedNodeId: null,
      liveSpec: null,
    }),

  pushEnvelope: (env) =>
    set((s) => {
      const nextEnvelopes = s.recentEnvelopes.length >= ENVELOPE_RING_CAP
        ? [...s.recentEnvelopes.slice(1), env]
        : [...s.recentEnvelopes, env];

      // Project run.status / run.metric envelopes into the per-node
      // status map so the canvas pills can switch on a stable
      // snapshot rather than reducing over the entire ring.
      const nextStatus = { ...s.nodeStatus };
      if (env.kind === "run.status" && env.node_id) {
        const existing = nextStatus[env.node_id] ?? { status: "pending" };
        nextStatus[env.node_id] = {
          ...existing,
          status: (env.state as LabNodeStatus | "pending") ?? existing.status,
          lastMetricAt: env.timestamp,
        };
      } else if (env.kind === "run.metric" && env.node_id) {
        const existing = nextStatus[env.node_id] ?? { status: "pending" };
        nextStatus[env.node_id] = {
          ...existing,
          lastMetricAt: env.timestamp,
          metrics: {
            ...(existing.metrics ?? {}),
            [env.name]: env.value,
          },
        };
      } else if (env.kind === "run.log" && env.level === "error" && env.node_id) {
        const existing = nextStatus[env.node_id] ?? { status: "pending" };
        nextStatus[env.node_id] = {
          ...existing,
          lastError: env.msg,
        };
      }

      // Keep currentRun in sync with terminal envelopes when the
      // route hasn't already refreshed via fetch.
      let nextCurrent = s.currentRun;
      if (
        env.kind === "run.status" &&
        env.run_id &&
        nextCurrent &&
        nextCurrent.id === env.run_id
      ) {
        nextCurrent = {
          ...nextCurrent,
          status: (env.state as LabRunOut["status"]) ?? nextCurrent.status,
        };
      }

      return {
        recentEnvelopes: nextEnvelopes,
        nodeStatus: nextStatus,
        currentRun: nextCurrent,
      };
    }),
}));

export type { NodeRuntimeState };
