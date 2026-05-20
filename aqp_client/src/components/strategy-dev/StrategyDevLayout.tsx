import { Outlet, useLocation } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";

import { RunKpiStrip } from "./RunKpiStrip";
import { StrategyDevProvider, useStrategyDev } from "./StrategyDevContext";
import { STRATEGY_DEV_ROUTES, StrategyDevSubNav } from "./SubNav";

/**
 * Master layout for the consolidated `/strategy-development/*` umbrella.
 * Renders a persistent left sub-nav + run-summary KPI strip and a
 * scrollable right pane that hosts the active child route. Wraps every
 * child in `StrategyDevProvider` so cross-route selections survive
 * navigation (per AGENTS.md hard-rule 5 spirit — context is
 * re-fetchable and idempotent; we just cache it for UX).
 */
export function StrategyDevLayout() {
  return (
    <StrategyDevProvider>
      <StrategyDevLayoutInner />
    </StrategyDevProvider>
  );
}

function StrategyDevLayoutInner() {
  const { pathname } = useLocation();
  const active = STRATEGY_DEV_ROUTES.find(
    (r) => pathname === r.to || pathname.startsWith(`${r.to}/`),
  );
  const { selection } = useStrategyDev();

  return (
    <div className="flex h-full min-h-0 w-full">
      <StrategyDevSubNav />
      <div className="flex min-h-0 flex-1 flex-col">
        <PageContainer
          title={
            <div className="flex items-center gap-2">
              <span>Strategy Development</span>
              {active ? (
                <Badge variant="secondary" className="text-[10px]">
                  {active.label}
                </Badge>
              ) : null}
            </div>
          }
          subtitle={
            active?.description ??
            "Consolidated workspace for strategy authoring, testing, and research-paper synthesis."
          }
          extra={
            selection.deploymentId ? (
              <Badge variant="outline" className="text-[10px]">
                deployment {selection.deploymentId.slice(0, 8)}
              </Badge>
            ) : null
          }
        >
          <div className="flex h-full min-h-0 flex-col gap-3">
            <RunKpiStrip />
            <div className="min-h-0 flex-1">
              <Outlet />
            </div>
          </div>
        </PageContainer>
      </div>
    </div>
  );
}

export { StrategyDevProvider, useStrategyDev } from "./StrategyDevContext";
