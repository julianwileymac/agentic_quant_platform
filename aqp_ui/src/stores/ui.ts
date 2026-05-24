"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIState {
  sidebarCollapsed: boolean;
  themeMode: "light" | "dark";
  assistantOpen: boolean;
  commandPaletteOpen: boolean;
  toggleSidebar: () => void;
  setTheme: (mode: "light" | "dark") => void;
  setAssistantOpen: (open: boolean) => void;
  setCommandPaletteOpen: (open: boolean) => void;
}

/**
 * Persisted UI state.
 * Mirrors aqp_client/src/store/ui.ts.
 */
export const useUiStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      themeMode: "dark",
      assistantOpen: false,
      commandPaletteOpen: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setTheme: (themeMode) => set({ themeMode }),
      setAssistantOpen: (assistantOpen) => set({ assistantOpen }),
      setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
    }),
    { name: "aqp-ui-state" },
  ),
);
