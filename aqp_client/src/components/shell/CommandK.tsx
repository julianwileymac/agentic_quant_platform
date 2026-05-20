import { Command } from "cmdk";
import { Search } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { Dialog, DialogContent } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/ui";

import { GROUP_ORDER, NAV_ITEMS, type NavGroup } from "./nav-config";

/**
 * Global command palette wired to Ctrl/Cmd+K. Backed by `cmdk` (the
 * shadcn-canonical primitive). Each nav item appears as a row; `Enter`
 * routes to it and dismisses the palette.
 */
export function CommandK() {
  const open = useUiStore((s) => s.commandPaletteOpen);
  const setOpen = useUiStore((s) => s.setCommandPaletteOpen);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, setOpen]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-xl gap-0 overflow-hidden p-0">
        <Command className="flex flex-col">
          <div className="flex items-center border-b border-[var(--border-default)] px-3">
            <Search className="mr-2 h-4 w-4 shrink-0 opacity-60" />
            <Command.Input
              placeholder="Jump to…"
              className="flex h-12 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-[var(--text-muted)] disabled:cursor-not-allowed disabled:opacity-50"
              autoFocus
            />
          </div>
          <Command.List className="max-h-[60vh] overflow-y-auto p-2">
            <Command.Empty className="px-2 py-6 text-center text-sm text-[var(--text-secondary)]">
              No matches found
            </Command.Empty>
            {GROUP_ORDER.map((group) => (
              <CommandGroup
                key={group}
                group={group}
                onSelect={(href) => {
                  setOpen(false);
                  navigate(href);
                }}
              />
            ))}
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}

interface CommandGroupProps {
  group: NavGroup;
  onSelect: (href: string) => void;
}

function CommandGroup({ group, onSelect }: CommandGroupProps) {
  const items = NAV_ITEMS.filter((n) => n.group === group);
  if (!items.length) return null;
  return (
    <Command.Group
      heading={
        <span className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
          {group}
        </span>
      }
    >
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <Command.Item
            key={item.key}
            value={`${item.label} ${item.href} ${item.group}`}
            onSelect={() => onSelect(item.href)}
            className={cn(
              "flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm outline-none",
              "data-[selected=true]:bg-[var(--bg-elevated)] data-[selected=true]:text-[var(--text-primary)]",
            )}
          >
            <Icon className="h-4 w-4 opacity-80" />
            <span className="flex-1">{item.label}</span>
            <span className="font-mono text-[10px] text-[var(--text-muted)]">{item.href}</span>
          </Command.Item>
        );
      })}
    </Command.Group>
  );
}
