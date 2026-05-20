import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui";

import {
  GROUP_ORDER,
  NAV_ITEMS,
  SUBMENU_ORDER,
  findActiveNavItem,
  getSubmenuIcon,
  type NavGroup,
  type NavItem,
  type NavSubmenu,
} from "./nav-config";

interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const { pathname } = useLocation();
  const [openSubmenus, setOpenSubmenus] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    for (const group of GROUP_ORDER) {
      for (const submenu of SUBMENU_ORDER) {
        if (NAV_ITEMS.some((n) => n.group === group && n.submenu === submenu)) {
          initial[`${group}-${submenu}`] = true;
        }
      }
    }
    return initial;
  });

  const active = useMemo(() => findActiveNavItem(pathname), [pathname]);

  return (
    <aside
      className={cn(
        "sticky left-0 top-0 z-30 flex h-screen shrink-0 flex-col border-r border-[var(--border-default)] bg-[var(--sidebar-bg)] text-sm transition-[width] duration-150",
        collapsed ? "w-[64px]" : "w-[232px]",
        className,
      )}
    >
      <div
        className={cn(
          "flex h-[52px] items-center border-b border-[var(--border-default)]",
          collapsed ? "justify-center" : "px-4",
        )}
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-[var(--info-fg)] to-indigo-500 text-sm font-semibold text-white">
          A
        </div>
        {!collapsed ? (
          <span className="ml-2 text-[15px] font-semibold tracking-tight">Quant Platform</span>
        ) : null}
      </div>

      <ScrollArea className="flex-1">
        <TooltipProvider delayDuration={150}>
          <nav className="px-2 py-2">
            {GROUP_ORDER.map((group) => {
              const groupItems = NAV_ITEMS.filter((n) => n.group === group);
              if (!groupItems.length) return null;
              const baseItems = groupItems.filter((n) => !n.submenu);
              const submenus = SUBMENU_ORDER.flatMap<NavSubmenu>((sm) =>
                groupItems.some((n) => n.submenu === sm) ? [sm] : [],
              );
              return (
                <div key={group} className="mb-3">
                  {!collapsed ? (
                    <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                      {group}
                    </div>
                  ) : null}
                  <ul className="flex flex-col gap-px">
                    {baseItems.map((item) => (
                      <SidebarItem key={item.key} item={item} active={active?.href === item.href} collapsed={collapsed} />
                    ))}
                    {submenus.map((submenu) => (
                      <SidebarSubmenu
                        key={`${group}-${submenu}`}
                        group={group}
                        submenu={submenu}
                        items={groupItems.filter((n) => n.submenu === submenu)}
                        active={active}
                        collapsed={collapsed}
                        open={openSubmenus[`${group}-${submenu}`] ?? true}
                        onToggle={() =>
                          setOpenSubmenus((prev) => ({
                            ...prev,
                            [`${group}-${submenu}`]: !(prev[`${group}-${submenu}`] ?? true),
                          }))
                        }
                      />
                    ))}
                  </ul>
                </div>
              );
            })}
          </nav>
        </TooltipProvider>
      </ScrollArea>
    </aside>
  );
}

interface SidebarItemProps {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
}

function SidebarItem({ item, active, collapsed }: SidebarItemProps) {
  const Icon = item.icon;
  const link = (
    <Link
      to={item.href}
      className={cn(
        "group flex h-8 items-center gap-2.5 rounded-md px-2 text-[var(--text-secondary)] transition-colors",
        "hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]",
        active && "bg-[var(--info-bg)] text-[var(--info-fg)]",
        collapsed && "justify-center px-0",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed ? <span className="truncate text-[13px]">{item.label}</span> : null}
    </Link>
  );
  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <li>{link}</li>
        </TooltipTrigger>
        <TooltipContent side="right">{item.label}</TooltipContent>
      </Tooltip>
    );
  }
  return <li>{link}</li>;
}

interface SidebarSubmenuProps {
  group: NavGroup;
  submenu: NavSubmenu;
  items: NavItem[];
  active: NavItem | undefined;
  collapsed: boolean;
  open: boolean;
  onToggle: () => void;
}

function SidebarSubmenu({ group, submenu, items, active, collapsed, open, onToggle }: SidebarSubmenuProps) {
  const Icon = getSubmenuIcon(submenu);
  const containsActive = items.some((i) => i.href === active?.href);
  if (collapsed) {
    return (
      <>
        {items.map((it) => (
          <SidebarItem key={it.key} item={it} active={active?.href === it.href} collapsed />
        ))}
      </>
    );
  }
  return (
    <li className="mt-1">
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-[12px] uppercase tracking-wide text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-elevated)]",
          containsActive && "text-[var(--info-fg)]",
        )}
        aria-expanded={open}
        aria-controls={`submenu-${group}-${submenu}`}
      >
        <Icon className="h-3.5 w-3.5" />
        <span className="flex-1 text-left">{submenu}</span>
        <ChevronDown className={cn("h-3 w-3 transition-transform", open ? "rotate-0" : "-rotate-90")} />
      </button>
      {open ? (
        <ul id={`submenu-${group}-${submenu}`} className="ml-3 mt-px flex flex-col gap-px">
          {items.map((it) => (
            <SidebarItem key={it.key} item={it} active={active?.href === it.href} collapsed={false} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}
