import { X } from "lucide-react";

import { ActionCenterPanel } from "@/components/action-center/ActionCenterPanel";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useUiStore } from "@/store/ui";

/**
 * Modal Action Center surfaced from the topbar bell. Renders the
 * same {@link ActionCenterPanel} as the dedicated `/action-center`
 * route, so behaviour is identical regardless of how the operator
 * gets there.
 */
export function ActionCenterDrawer() {
  const open = useUiStore((s) => s.actionCenterOpen);
  const setOpen = useUiStore((s) => s.setActionCenterOpen);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="flex h-[85vh] w-[min(95vw,1100px)] max-w-none flex-col gap-3 p-4">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <div>
              <DialogTitle>Action Center</DialogTitle>
              <DialogDescription>
                Review every agent-proposed trade. Each approval / decline is logged on
                <code className="mx-1 rounded bg-[var(--bg-app)] px-1 font-mono text-xs">
                  agent_runs_v2
                </code>
                via AgentRuntime.
              </DialogDescription>
            </div>
            <Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label="Close">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </DialogHeader>
        <div className="flex-1 min-h-0">
          <ActionCenterPanel embedded />
        </div>
      </DialogContent>
    </Dialog>
  );
}
