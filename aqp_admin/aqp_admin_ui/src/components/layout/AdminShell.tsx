import { Building2, LayoutDashboard, ServerCog } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

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
];

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/30 p-4">
        <div className="mb-6 px-2 text-lg font-semibold tracking-tight">AQP Admin</div>
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
      <main className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  );
}
