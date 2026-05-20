import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeMode = "light" | "dark";

interface UiState {
  themeMode: ThemeMode;
  sidebarCollapsed: boolean;
  assistantOpen: boolean;
  commandPaletteOpen: boolean;
  actionCenterOpen: boolean;
  setThemeMode: (mode: ThemeMode) => void;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setAssistantOpen: (open: boolean) => void;
  setCommandPaletteOpen: (open: boolean) => void;
  setActionCenterOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set, get) => ({
      themeMode: "dark",
      sidebarCollapsed: false,
      assistantOpen: false,
      commandPaletteOpen: false,
      actionCenterOpen: false,
      setThemeMode: (mode) => set({ themeMode: mode }),
      toggleTheme: () => set({ themeMode: get().themeMode === "dark" ? "light" : "dark" }),
      toggleSidebar: () => set({ sidebarCollapsed: !get().sidebarCollapsed }),
      setAssistantOpen: (open) => set({ assistantOpen: open }),
      setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
      setActionCenterOpen: (open) => set({ actionCenterOpen: open }),
    }),
    {
      name: "aqp-ui",
      partialize: (state) => ({
        themeMode: state.themeMode,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    },
  ),
);
