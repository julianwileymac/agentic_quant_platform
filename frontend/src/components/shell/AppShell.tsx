import { Outlet } from "react-router-dom";

import { ActionCenterDrawer } from "@/components/action-center/ActionCenterDrawer";
import { ProposalToastBus } from "@/components/action-center/ProposalToastBus";
import { SandboxBanner } from "@/components/common/SandboxBanner";
import { useProposalsStream } from "@/lib/ws/useProposalsStream";

import { AssistantDrawer } from "./AssistantDrawer";
import { CommandK } from "./CommandK";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

/**
 * Outer app shell wired into React Router 7. Renders the sidebar /
 * topbar around an <Outlet/>, mounts global overlays (CommandK,
 * AssistantDrawer, SandboxBanner, ActionCenterDrawer, ProposalToastBus),
 * and opens the proposals WebSocket once for the lifetime of the app.
 */
export function AppShell() {
  // Single global subscription to /agents/proposals/stream — every
  // route shares the same Zustand-backed proposals queue.
  useProposalsStream();
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <TopBar />
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
