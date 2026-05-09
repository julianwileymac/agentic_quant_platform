import { Check, ChevronDown, FlaskConical, Radio, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTenancyStore, type ExecutionMode } from "@/store/tenancy";

const MODE_OPTIONS: ReadonlyArray<{ id: ExecutionMode; label: string; icon: typeof Radio }> = [
  { id: "live", label: "Live execution", icon: Radio },
  { id: "paper", label: "Paper trading", icon: ShieldAlert },
  { id: "sandbox", label: "Sandbox simulation", icon: FlaskConical },
];

export function WorkspaceSwitcher() {
  const workspaceId = useTenancyStore((s) => s.workspaceId);
  const projectId = useTenancyStore((s) => s.projectId);
  const labId = useTenancyStore((s) => s.labId);
  const mode = useTenancyStore((s) => s.mode);
  const setMode = useTenancyStore((s) => s.setMode);

  const label =
    projectId && labId
      ? `${shortId(workspaceId)} / ${shortId(projectId)} / ${shortId(labId)}`
      : projectId
        ? `${shortId(workspaceId)} / ${shortId(projectId)}`
        : workspaceId
          ? shortId(workspaceId)
          : "default";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2 text-xs">
          <span className="font-mono opacity-80">{label}</span>
          <ChevronDown className="h-3 w-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Execution mode</DropdownMenuLabel>
        {MODE_OPTIONS.map((opt) => {
          const Icon = opt.icon;
          const active = opt.id === mode;
          return (
            <DropdownMenuItem
              key={opt.id}
              onSelect={(e) => {
                e.preventDefault();
                setMode(opt.id);
              }}
            >
              <Icon className="h-4 w-4" />
              <span className="flex-1">{opt.label}</span>
              {active ? <Check className="h-3.5 w-3.5 text-[var(--info-fg)]" /> : null}
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Tenancy</DropdownMenuLabel>
        <DropdownMenuItem disabled className="font-mono text-xs">
          workspace: {shortId(workspaceId)}
        </DropdownMenuItem>
        <DropdownMenuItem disabled className="font-mono text-xs">
          project: {shortId(projectId)}
        </DropdownMenuItem>
        <DropdownMenuItem disabled className="font-mono text-xs">
          lab: {shortId(labId)}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.split("-")[0] ?? id.slice(0, 8);
}
