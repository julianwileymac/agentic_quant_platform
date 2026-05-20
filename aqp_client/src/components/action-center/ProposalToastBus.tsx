import { useEffect, useRef } from "react";

import { toast } from "@/components/ui/toast";
import { useProposalsStore, type AgentProposal } from "@/store/proposals";
import { useUiStore } from "@/store/ui";

/**
 * Bridges the proposals store to the toast layer. Whenever a new
 * pending proposal lands, fires a high-priority toast that links to
 * the Action Center. The toast itself does NOT approve the proposal;
 * approval always goes through {@link ConfirmFrictionDialog} so the
 * blueprint's purposeful-friction requirement is preserved.
 */
export function ProposalToastBus() {
  const seenRef = useRef<Set<string>>(new Set());
  const setOpen = useUiStore((s) => s.setActionCenterOpen);

  useEffect(() => {
    const unsubscribe = useProposalsStore.subscribe((state, prev) => {
      if (state.pending === prev.pending) return;
      const seen = seenRef.current;
      for (const proposal of state.pending) {
        if ((proposal.status ?? "pending") !== "pending") continue;
        if (seen.has(proposal.id)) continue;
        seen.add(proposal.id);
        emitToast(proposal, () => setOpen(true));
      }
    });
    return () => unsubscribe();
  }, [setOpen]);

  return null;
}

function emitToast(proposal: AgentProposal, openCenter: () => void) {
  const headline = `${proposal.agent} proposes ${proposal.side.toUpperCase()} ${proposal.vt_symbol}`;
  toast.warning(headline, {
    description:
      proposal.rationale ??
      `Pending human approval. Confidence ${
        proposal.confidence != null ? (proposal.confidence * 100).toFixed(1) : "?"
      }%.`,
    duration: 12_000,
    action: {
      label: "Review",
      onClick: openCenter,
    },
  });
}
