import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * Active tenancy + execution-mode context held in the browser. Mirrors
 * the request headers expected by FastAPI (X-AQP-Workspace, X-AQP-Project,
 * X-AQP-Lab, X-AQP-User) so the api client can inject them on every
 * fetch without per-call wiring. Defaults match the deterministic seed
 * from alembic migration 0017.
 */
export const DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001";
export const DEFAULT_TEAM_ID = "00000000-0000-0000-0000-000000000002";
export const DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003";
export const DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004";
export const DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005";
export const DEFAULT_LAB_ID = "00000000-0000-0000-0000-000000000006";

/**
 * Execution mode. Controls the SandboxBanner amber accent and the
 * "Simulated execution" caption applied to order tickets / approval
 * buttons. Server-side gating is independently enforced; this is a UX
 * affordance, not a security boundary.
 */
export type ExecutionMode = "live" | "paper" | "sandbox";

export interface TenancyState {
  userId: string | null;
  orgId: string | null;
  teamId: string | null;
  workspaceId: string | null;
  projectId: string | null;
  labId: string | null;
  mode: ExecutionMode;
  setWorkspace: (id: string | null) => void;
  setProject: (id: string | null) => void;
  setLab: (id: string | null) => void;
  setUser: (id: string | null) => void;
  setOrg: (id: string | null) => void;
  setMode: (mode: ExecutionMode) => void;
  reset: () => void;
}

const ENV_DEFAULT_MODE = (() => {
  const raw = (import.meta.env.VITE_DEFAULT_MODE ?? "").toLowerCase();
  return raw === "paper" || raw === "sandbox" ? (raw as ExecutionMode) : "live";
})();

export const useTenancyStore = create<TenancyState>()(
  persist(
    (set) => ({
      userId: DEFAULT_USER_ID,
      orgId: DEFAULT_ORG_ID,
      teamId: DEFAULT_TEAM_ID,
      workspaceId: DEFAULT_WORKSPACE_ID,
      projectId: DEFAULT_PROJECT_ID,
      labId: DEFAULT_LAB_ID,
      mode: ENV_DEFAULT_MODE,
      setWorkspace: (id) => set({ workspaceId: id, projectId: null, labId: null }),
      setProject: (id) => set({ projectId: id }),
      setLab: (id) => set({ labId: id }),
      setUser: (id) => set({ userId: id }),
      setOrg: (id) => set({ orgId: id }),
      setMode: (mode) => set({ mode }),
      reset: () =>
        set({
          userId: DEFAULT_USER_ID,
          orgId: DEFAULT_ORG_ID,
          teamId: DEFAULT_TEAM_ID,
          workspaceId: DEFAULT_WORKSPACE_ID,
          projectId: DEFAULT_PROJECT_ID,
          labId: DEFAULT_LAB_ID,
          mode: ENV_DEFAULT_MODE,
        }),
    }),
    {
      name: "aqp-tenancy",
      partialize: (state) => ({
        userId: state.userId,
        orgId: state.orgId,
        teamId: state.teamId,
        workspaceId: state.workspaceId,
        projectId: state.projectId,
        labId: state.labId,
        mode: state.mode,
      }),
    },
  ),
);

/**
 * Read the active tenancy headers as a plain object — safe to call
 * from non-React contexts (the api client uses this on every request).
 */
export function getTenancyHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const state = useTenancyStore.getState();
  const headers: Record<string, string> = {};
  if (state.userId) headers["X-AQP-User"] = state.userId;
  if (state.workspaceId) headers["X-AQP-Workspace"] = state.workspaceId;
  if (state.projectId) headers["X-AQP-Project"] = state.projectId;
  if (state.labId) headers["X-AQP-Lab"] = state.labId;
  headers["X-AQP-Mode"] = state.mode;
  return headers;
}
