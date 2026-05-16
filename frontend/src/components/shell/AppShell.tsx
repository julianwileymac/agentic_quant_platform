import { Outlet } from "react-router-dom";

import { ActionCenterDrawer } from "@/components/action-center/ActionCenterDrawer";
import { ProposalToastBus } from "@/components/action-center/ProposalToastBus";
import { SandboxBanner } from "@/components/common/SandboxBanner";
import { useClaimsToTenancy } from "@/lib/auth/useClaimsToTenancy";
import { useProposalsStream } from "@/lib/ws/useProposalsStream";

import { AssistantDrawer } from "./AssistantDrawer";
import { CommandK } from "./CommandK";
import { ContextBar } from "./ContextBar";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

/**
 * Outer app shell wired into React Router 7. Renders the sidebar /
 * topbar around an <Outlet/>, mounts global overlays (CommandK,
 * AssistantDrawer, SandboxBanner, ActionCenterDrawer, ProposalToastBus),
 * and opens the proposals WebSocket once for the lifetime of the app.
 *
 * The Phase 6 ContextBar sits between the TopBar and SandboxBanner
 * so the multi-tenant context indicator is always visible without
 * crowding the always-on amber sandbox/paper accent.
 */
export function AppShell() {
  // Single global subscription to /agents/proposals/stream — every
  // route shares the same Zustand-backed proposals queue.
  useProposalsStream();
  // Hydrate the tenancy store from Auth0 custom claims on login.
  useClaimsToTenancy();
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <TopBar />
        <ContextBar />
        <SandboxBanner />
        <main className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <CommandK />
      <AssistantDrawer />
      <ActionCenterDrawer />
      <ProposalToastBus />
    </div>
  );
}
