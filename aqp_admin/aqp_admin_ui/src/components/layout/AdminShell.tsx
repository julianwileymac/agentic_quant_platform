import {
  Activity,
  Building2,
  FileText,
  LayoutDashboard,
  Package,
  ServerCog,
  Users,
} from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { KillSwitch } from "@/components/common/KillSwitch";
import { SandboxBadge } from "@/components/common/SandboxBadge";
import { cn } from "@/lib/cn";

interface NavItem {
  to: string;
  label: string;
  Icon: typeof LayoutDashboard;
}

const NAV: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", Icon: LayoutDashboard },
  { to: "/accounts", label: "Accounts", Icon: Building2 },
  { to: "/services", label: "Services", Icon: ServerCog },
  { to: "/tenants/new", label: "Vend tenant", Icon: Users },
  { to: "/builds", label: "Builds", Icon: Package },
  { to: "/runbooks", label: "Runbooks", Icon: FileText },
  { to: "/audit", label: "Audit", Icon: Activity },
];

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/30 p-4">
        <div className="mb-6 flex items-center px-2 text-lg font-semibold tracking-tight">
          AQP Admin
          <SandboxBadge />
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  isActive ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
                )
              }
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-2 text-xs text-muted-foreground">v0.1.0</div>
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
