import { BellRing, Menu, MessageSquare, Moon, PanelLeft, Search, Sun } from "lucide-react";
import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { KillSwitch } from "@/components/common/KillSwitch";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { usePendingCount } from "@/store/proposals";
import { useTenancyStore, type ExecutionMode } from "@/store/tenancy";
import { useUiStore } from "@/store/ui";

import { findActiveNavItem } from "./nav-config";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

const MODE_TONE: Record<ExecutionMode, "positive" | "warn"> = {
  live: "positive",
  paper: "warn",
  sandbox: "warn",
};

export function TopBar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const themeMode = useUiStore((s) => s.themeMode);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const setAssistantOpen = useUiStore((s) => s.setAssistantOpen);
  const assistantOpen = useUiStore((s) => s.assistantOpen);
  const setCommandPaletteOpen = useUiStore((s) => s.setCommandPaletteOpen);
  const setActionCenterOpen = useUiStore((s) => s.setActionCenterOpen);
  const mode = useTenancyStore((s) => s.mode);
  const pending = usePendingCount();
  const { pathname } = useLocation();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandPaletteOpen(true);
      } else if (isMod && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setAssistantOpen(!assistantOpen);
      } else if (isMod && e.shiftKey && e.key.toLowerCase() === "a") {
        e.preventDefault();
        setActionCenterOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [assistantOpen, setActionCenterOpen, setAssistantOpen, setCommandPaletteOpen]);

  const matched = findActiveNavItem(pathname);

  return (
    <header
      data-topbar="true"
      className={cn(
        "sticky top-0 z-20 flex h-[52px] items-center gap-3 border-b border-[var(--topbar-border)] bg-[var(--topbar-bg)] px-3",
      )}
    >
      <Button
        variant="ghost"
        size="icon"
        onClick={toggleSidebar}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <Menu className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
      </Button>
      <div className="hidden items-center gap-2 md:flex">
        <span className="text-sm font-semibold tracking-tight">{matched?.label ?? "Workspace"}</span>
        <Badge variant={MODE_TONE[mode]} className="uppercase">
          {mode}
        </Badge>
      </div>
      <div className="ml-2 hidden md:block">
        <WorkspaceSwitcher />
      </div>

      <div className="flex-1" />

      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setCommandPaletteOpen(true)}
              className="gap-2 text-[var(--text-secondary)]"
            >
              <Search className="h-4 w-4" />
              <span className="hidden sm:inline">Search</span>
              <kbd className="hidden rounded border border-[var(--border-default)] px-1 text-[10px] sm:inline">
                Ctrl K
              </kbd>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Command palette (Ctrl/Cmd+K)</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setActionCenterOpen(true)}
              aria-label="Open Action Center"
              className="relative"
            >
              <BellRing className="h-4 w-4" />
              {pending > 0 ? (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--neg-fg)] px-1 text-[10px] font-bold text-white">
                  {pending > 99 ? "99+" : pending}
                </span>
              ) : null}
            </Button>
          </TooltipTrigger>
          <TooltipContent>Action Center (Ctrl/Cmd+Shift+A)</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
              {themeMode === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>Toggle theme</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setAssistantOpen(!assistantOpen)}
              aria-label="Open assistant"
              className={cn(assistantOpen && "text-[var(--info-fg)]")}
            >
              <MessageSquare className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Assistant (Ctrl/Cmd+J)</TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <KillSwitch />
    </header>
  );
}
