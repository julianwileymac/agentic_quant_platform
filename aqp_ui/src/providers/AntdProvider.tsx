"use client";

import { ConfigProvider, theme } from "antd";
import { useEffect, useState } from "react";

interface AntdProviderProps {
  children: React.ReactNode;
  /** Force a theme mode; defaults to user/system preference. */
  themeMode?: "light" | "dark";
}

/**
 * Wraps the app in Ant Design's ConfigProvider with AQP design tokens.
 *
 * Theme mode resolution:
 *   1. Explicit `themeMode` prop (used by the dashboard layout to force dark).
 *   2. `aqp-ui-theme` localStorage entry (matches aqp_client's useUiStore).
 *   3. `prefers-color-scheme` media query.
 *   4. Default `dark`.
 */
export function AntdProvider({ children, themeMode }: AntdProviderProps) {
  const [resolvedMode, setResolvedMode] = useState<"light" | "dark">(
    themeMode ?? "dark",
  );

  useEffect(() => {
    if (themeMode) {
      setResolvedMode(themeMode);
      return;
    }
    try {
      const stored = window.localStorage.getItem("aqp-ui-theme");
      if (stored === "light" || stored === "dark") {
        setResolvedMode(stored);
        return;
      }
    } catch {
      // localStorage unavailable; fall through.
    }
    const prefersLight = window.matchMedia(
      "(prefers-color-scheme: light)",
    ).matches;
    setResolvedMode(prefersLight ? "light" : "dark");
  }, [themeMode]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolvedMode === "dark");
    document.documentElement.classList.toggle("light", resolvedMode === "light");
  }, [resolvedMode]);

  return (
    <ConfigProvider
      theme={{
        algorithm:
          resolvedMode === "dark" ? theme.darkAlgorithm : theme.defaultAlgorithm,
        cssVar: true,
        hashed: false,
        token: {
          colorPrimary: "#1677ff",
          colorSuccess: "#10b981",
          colorWarning: "#f59e0b",
          colorError: "#ef4444",
          colorInfo: "#3b82f6",
          borderRadius: 4,
          fontFamily:
            "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
        },
        components: {
          Layout: {
            headerBg: "var(--bg-surface)",
            siderBg: "var(--bg-surface)",
            bodyBg: "var(--bg-app)",
            footerBg: "var(--bg-surface)",
          },
          Card: {
            colorBgContainer: "var(--bg-surface)",
          },
        },
      }}
    >
      {children}
    </ConfigProvider>
  );
}
