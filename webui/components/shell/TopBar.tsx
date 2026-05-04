"use client";

import {
  BulbFilled,
  BulbOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { Badge, Button, Layout, Space, Tooltip, Typography } from "antd";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { useUiStore } from "@/lib/store/ui";

import { NAV_ITEMS } from "./nav-config";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

const { Header } = Layout;
const { Text } = Typography;

export function TopBar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const themeMode = useUiStore((s) => s.themeMode);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const setAssistantOpen = useUiStore((s) => s.setAssistantOpen);
  const assistantOpen = useUiStore((s) => s.assistantOpen);
  const setCommandPaletteOpen = useUiStore((s) => s.setCommandPaletteOpen);
  const pathname = usePathname();

  const matched = NAV_ITEMS.filter(
    (n) => pathname === n.href || pathname.startsWith(n.href + "/"),
  )
    .sort((a, b) => b.href.length - a.href.length)
    .at(0);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
      if (isMod && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setAssistantOpen(!assistantOpen);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [assistantOpen, setAssistantOpen, setCommandPaletteOpen]);

  return (
    <Header
      style={{
        padding: "0 16px",
        borderBottom: "1px solid var(--ant-color-border, #e5e7eb)",
        display: "flex",
        alignItems: "center",
        gap: 12,
        position: "sticky",
        top: 0,
        zIndex: 10,
      }}
    >
      <Button
        type="text"
        icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        onClick={toggleSidebar}
        aria-label="Toggle sidebar"
      />
      <Text strong style={{ fontSize: 15 }}>
        {matched?.label ?? "Workspace"}
      </Text>
      <div style={{ width: 16 }} />
      <WorkspaceSwitcher />
      <div style={{ flex: 1 }} />
      <Space size={4}>
        <Tooltip title="Command palette (Ctrl/Cmd+K)">
          <Button
            type="text"
            icon={<SearchOutlined />}
            onClick={() => setCommandPaletteOpen(true)}
          >
            <span style={{ opacity: 0.7, fontSize: 12 }}>Search</span>
          </Button>
        </Tooltip>
        <Tooltip title="Toggle theme">
          <Button
            type="text"
            icon={themeMode === "dark" ? <BulbFilled /> : <BulbOutlined />}
            onClick={toggleTheme}
            aria-label="Toggle theme"
          />
        </Tooltip>
        <Tooltip title="Assistant (Ctrl/Cmd+J)">
          <Badge dot={assistantOpen} color="blue">
            <Button
              type="text"
              icon={<MessageOutlined />}
              onClick={() => setAssistantOpen(!assistantOpen)}
              aria-label="Open assistant"
            />
          </Badge>
        </Tooltip>
      </Space>
    </Header>
  );
}
