"use client";

import { Layout, Menu, Tooltip, Typography } from "antd";
import { usePathname, useRouter } from "next/navigation";
import { useMemo } from "react";

import { useUiStore } from "@/lib/store/ui";

import { NAV_ITEMS, type NavItem } from "./nav-config";

const { Sider } = Layout;
const { Text } = Typography;

const GROUP_ORDER: NavItem["group"][] = [
  "Workspace",
  "Agents",
  "RAG",
  "Research",
  "Lab",
  "Execution",
  "Workflows",
  "System",
];

export function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const pathname = usePathname();
  const router = useRouter();

  const items = useMemo(() => {
    return GROUP_ORDER.map((group) => ({
      key: `group-${group}`,
      type: "group" as const,
      label: collapsed ? null : (
        <Text type="secondary" style={{ fontSize: 11, letterSpacing: 1, textTransform: "uppercase" }}>
          {group}
        </Text>
      ),
      children: NAV_ITEMS.filter((n) => n.group === group).map((n) => ({
        key: n.href,
        icon: collapsed ? (
          <Tooltip title={n.label} placement="right">
            <span>{n.icon}</span>
          </Tooltip>
        ) : (
          n.icon
        ),
        label: n.label,
      })),
    }));
  }, [collapsed]);

  const selected = useMemo(() => {
    const match = NAV_ITEMS.filter((n) => pathname === n.href || pathname.startsWith(n.href + "/"))
      .sort((a, b) => b.href.length - a.href.length)
      .at(0);
    return match ? [match.href] : [];
  }, [pathname]);

  return (
    <Sider
      collapsed={collapsed}
      collapsible={false}
      width={232}
      collapsedWidth={64}
      style={{
        borderRight: "1px solid var(--ant-color-border, #e5e7eb)",
        height: "100vh",
        overflow: "hidden",
        position: "sticky",
        top: 0,
        left: 0,
      }}
    >
      <div
        style={{
          height: 52,
          display: "flex",
          alignItems: "center",
          justifyContent: collapsed ? "center" : "flex-start",
          padding: collapsed ? 0 : "0 16px",
          borderBottom: "1px solid var(--ant-color-border, #e5e7eb)",
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background: "linear-gradient(135deg, #3b82f6, #6366f1)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontWeight: 700,
            marginRight: collapsed ? 0 : 10,
          }}
        >
          A
        </div>
        {!collapsed ? (
          <Text strong style={{ fontSize: 15 }}>
            Quant Platform
          </Text>
        ) : null}
      </div>
      <div style={{ height: "calc(100vh - 52px)", overflowY: "auto" }}>
        <Menu
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={selected}
          onClick={({ key }) => router.push(key as string)}
          items={items}
          style={{ borderRight: 0, paddingTop: 8, paddingBottom: 24 }}
        />
      </div>
    </Sider>
  );
}
