import { useEffect } from "react";
import { Navigate, Outlet, useParams } from "react-router-dom";

import { LabShell } from "@/features/data-lab/shell/LabShell";
import { useLabStore } from "@/features/data-lab/state/labStore";
import type { LabMode } from "@/lib/api/lab";

interface LabWorkspaceRouteProps {
  /** Optional mode override; otherwise read from the :mode segment. */
  mode?: LabMode;
}

/**
 * Data Lab workspace route — mounted at `/labs/:lab_id/workspace[/:mode]`.
 *
 * The shell owns the 4-mode tab bar, content-hash badge, RunHistory
 * drawer slot, and the multiplexed /ws/lab/{session_id} subscription.
 * Each mode renders its own canvas inside the shell's `<main>`.
 *
 * When no explicit `:mode` is in the URL we redirect to `/testing`,
 * the most-used mode and the one with the closest legacy precedent
 * (the existing Workflow Studio and Strategy Composer canvases).
 */
export function LabWorkspaceRoute({ mode }: LabWorkspaceRouteProps = {}) {
  const { lab_id, mode: modeSegment } = useParams<{ lab_id: string; mode?: string }>();
  const setMode = useLabStore((s) => s.setMode);

  // Resolve the active mode from props OR URL segment, defaulting to testing.
  const resolvedMode: LabMode | null = (() => {
    if (mode) return mode;
    if (modeSegment === "eda") return "eda";
    if (modeSegment === "testing") return "testing";
    if (modeSegment === "evaluation") return "evaluation";
    if (modeSegment === "simulation") return "simulation";
    return null;
  })();

  useEffect(() => {
    if (resolvedMode) {
      setMode(resolvedMode);
    }
  }, [resolvedMode, setMode]);

  if (!lab_id) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        Missing lab id. Pick a lab from <code>/admin/labs</code> to open the workspace.
      </div>
    );
  }

  // Redirect /labs/:id/workspace -> /labs/:id/workspace/testing.
  if (!resolvedMode) {
    return <Navigate to={`/labs/${lab_id}/workspace/testing`} replace />;
  }

  return (
    <LabShell>
      <Outlet />
    </LabShell>
  );
}

export default LabWorkspaceRoute;
