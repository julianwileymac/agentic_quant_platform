"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Layout, Menu, type MenuProps } from "antd";
import {
  Activity,
  BarChart3,
  Beaker,
  Bot,
  Boxes,
  Database,
  GitBranch,
  Home,
  LineChart,
  Microscope,
  Network,
  Settings,
  TrendingUp,
  Wrench,
} from "lucide-react";

import { useUiStore } from "@/stores/ui";
import { useTenancyStore } from "@/stores/tenancy";
import { useAuth } from "@/hooks/useAuth";
import { KillSwitch } from "@/components/common/KillSwitch";
import { OrgSwitcher } from "@/components/shell/OrgSwitcher";

const { Header, Sider, Content } = Layout;

type NavItem = NonNullable<MenuProps["items"]>[number];

function navItem(key: string, label: string, Icon: React.ElementType): NavItem {
  return {
    key,
    icon: <Icon size={16} />,
    label: <Link href={key}>{label}</Link>,
  };
}

const NAV: NavItem[] = [
  navItem("/dashboard", "Dashboard", Home),
  navItem("/strategies", "Strategies", LineChart),
  navItem("/paper-runs", "Paper runs", Activity),
  navItem("/backtests", "Backtests", BarChart3),
  navItem("/data", "Data", Database),
  navItem("/ml", "ML", Boxes),
  navItem("/agents", "Agents", Bot),
  navItem("/workflows", "Workflows", GitBranch),
  navItem("/labs", "Labs", Beaker),
  navItem("/analytics", "Analytics", TrendingUp),
  navItem("/research", "Research", Microscope),
  navItem("/portfolio", "Portfolio", Network),
];

const SETTINGS: NavItem[] = [navItem("/settings/team", "Settings", Settings)];

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const sidebarCollapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const mode = useTenancyStore((s) => s.mode);
  const { isAuthenticated, user } = useAuth();

  const selectedKey = NAV.concat(SETTINGS)
    .map((n) => n?.key as string)
    .filter(Boolean)
    .find((key) => pathname === key || pathname.startsWith(`${key}/`));

  return (
    <Layout
      style={{
        minHeight: "100vh",
        background: "var(--bg-app)",
      }}
    >
      <Sider
        theme="dark"
        collapsible
        collapsed={sidebarCollapsed}
        onCollapse={toggleSidebar}
        width={220}
        style={{ background: "var(--bg-surface)", borderRight: "1px solid var(--border-default)" }}
      >
        <div className="flex h-12 items-center gap-2 px-4">
          <Wrench size={18} style={{ color: "var(--accent-primary)" }} />
          {!sidebarCollapsed ? (
            <span className="text-sm font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
              AQP
            </span>
          ) : null}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selectedKey ? [selectedKey] : []}
          items={NAV}
          style={{ background: "var(--bg-surface)", borderInlineEnd: "none" }}
        />
        <div className="mt-auto">
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={selectedKey ? [selectedKey] : []}
            items={SETTINGS}
            style={{ background: "var(--bg-surface)", borderInlineEnd: "none" }}
          />
        </div>
      </Sider>

      <Layout style={{ background: "var(--bg-app)" }}>
        <Header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 24px",
            background: "var(--bg-surface)",
            borderBottom: "1px solid var(--border-default)",
          }}
        >
          <div className="flex items-center gap-3">
            <OrgSwitcher />
            <ModeChip mode={mode} />
          </div>
          <div className="flex items-center gap-3">
            <KillSwitch />
            <UserBadge name={user?.name ?? user?.email ?? ""} authenticated={isAuthenticated} />
          </div>
        </Header>
        <Content style={{ padding: 24 }}>{children}</Content>
      </Layout>
    </Layout>
  );
}

function ModeChip({ mode }: { mode: "live" | "paper" | "sandbox" }) {
  const colors = {
    live: { bg: "rgba(16, 185, 129, 0.15)", fg: "var(--pos-fg)", label: "LIVE" },
    paper: { bg: "rgba(245, 158, 11, 0.12)", fg: "var(--warn-fg)", label: "PAPER" },
    sandbox: { bg: "rgba(245, 158, 11, 0.12)", fg: "var(--warn-fg)", label: "SANDBOX" },
  } as const;
  const c = colors[mode];
  return (
    <span
      className="rounded px-2 py-1 text-xs font-semibold tracking-wider"
      style={{ background: c.bg, color: c.fg }}
    >
      {c.label}
    </span>
  );
}

function UserBadge({ name, authenticated }: { name: string; authenticated: boolean }) {
  if (!authenticated) {
    return (
      <Link href="/login" style={{ color: "var(--text-secondary)" }} className="text-sm">
        Sign in
      </Link>
    );
  }
  return (
    <Link
      href="/settings/profile"
      className="flex items-center gap-2 rounded px-2 py-1 text-sm transition-colors hover:bg-white/5"
      style={{ color: "var(--text-primary)" }}
    >
      <span
        className="flex h-6 w-6 items-center justify-center rounded-full text-xs"
        style={{ background: "var(--bg-elevated)", color: "var(--text-primary)" }}
      >
        {(name[0] ?? "?").toUpperCase()}
      </span>
      <span className="hidden md:inline">{name}</span>
    </Link>
  );
}
