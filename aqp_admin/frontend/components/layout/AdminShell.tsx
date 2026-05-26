"use client";

/**
 * AdminShell — sidebar nav + topbar + kill-switch.
 *
 * Ported from `aqp_admin_ui/src/components/layout/AdminShell.tsx`.
 * Differences vs. the Vite original:
 *
 * - `react-router-dom` `<NavLink>` → Next.js `<Link>` + `usePathname`
 * - props are typed `ReactNode` (children pattern remains)
 * - icons unchanged (lucide-react renders identically)
 * - new nav entries for the 6 added modules (secrets / lineage /
 *   models / paper / rbac / accounts-mode)
 */
import {
  Activity,
  Boxes,
  Building2,
  Coins,
  FileText,
  GitBranch,
  KeyRound,
  LayoutDashboard,
  Network,
  Package,
  ServerCog,
  Settings,
  ShieldCheck,
  TerminalSquare,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { KillSwitch } from "@/components/common/KillSwitch";
import { SandboxBadge } from "@/components/common/SandboxBadge";
import { cn } from "@/lib/cn";

interface NavItem {
  to: string;
  label: string;
  Icon: typeof LayoutDashboard;
}

const NAV: readonly NavItem[] = [
  { to: "/dashboard", label: "Dashboard", Icon: LayoutDashboard },
  { to: "/accounts", label: "Accounts", Icon: Building2 },
  { to: "/services", label: "Services", Icon: ServerCog },
  { to: "/terraform", label: "Terraform", Icon: TerminalSquare },
  { to: "/kubernetes", label: "Kubernetes", Icon: Network },
  { to: "/secrets", label: "Secrets", Icon: KeyRound },
  { to: "/lineage", label: "Lineage", Icon: GitBranch },
  { to: "/models", label: "Models", Icon: Boxes },
  { to: "/paper", label: "Paper trading", Icon: Coins },
  { to: "/rbac", label: "RBAC", Icon: ShieldCheck },
  { to: "/settings", label: "Settings", Icon: Settings },
  { to: "/tenants/new", label: "Vend tenant", Icon: Users },
  { to: "/builds", label: "Builds", Icon: Package },
  { to: "/runbooks", label: "Runbooks", Icon: FileText },
  { to: "/audit", label: "Audit", Icon: Activity },
];

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/30 p-4">
        <div className="mb-6 flex items-center px-2 text-lg font-semibold tracking-tight">
          AQP Admin
          <SandboxBadge />
        </div>
        <nav className="flex flex-col gap-1 overflow-y-auto">
          {NAV.map(({ to, label, Icon }) => {
            const isActive = pathname === to || pathname?.startsWith(`${to}/`);
            return (
              <Link
                key={to}
                href={to}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  isActive ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
                )}
              >
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto px-2 text-xs text-muted-foreground">v0.2.0</div>
      </aside>
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b bg-white px-6 py-3">
          <div className="text-sm text-muted-foreground">Internal admin surface</div>
          <KillSwitch />
        </header>
        <main className="flex-1 overflow-auto p-8">{children}</main>
      </div>
    </div>
  );
}
