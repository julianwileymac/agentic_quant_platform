"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface TenancyState {
  orgId: string | null;
  workspaceId: string | null;
  projectId: string | null;
  labId: string | null;
  mode: "live" | "paper" | "sandbox";
  setActiveOrg: (id: string | null) => void;
  setActiveWorkspace: (id: string | null) => void;
  setActiveProject: (id: string | null) => void;
  setActiveLab: (id: string | null) => void;
  setMode: (m: "live" | "paper" | "sandbox") => void;
}

/**
 * Active tenancy context. Hydrated from JWT claims via the
 * AuthClientProvider on initial mount; users can switch active
 * workspace / project / lab via the dashboard shell's switchers.
 *
 * Mirrors aqp_client/src/store/tenancy.ts.
 */
export const useTenancyStore = create<TenancyState>()(
  persist(
    (set) => ({
      orgId: null,
      workspaceId: null,
      projectId: null,
      labId: null,
      mode: "paper",
      setActiveOrg: (orgId) => set({ orgId }),
      setActiveWorkspace: (workspaceId) => set({ workspaceId }),
      setActiveProject: (projectId) => set({ projectId }),
      setActiveLab: (labId) => set({ labId }),
      setMode: (mode) => {
        set({ mode });
        if (typeof document !== "undefined") {
          document.documentElement.setAttribute("data-mode", mode);
        }
      },
    }),
    { name: "aqp-ui-tenancy" },
  ),
);
