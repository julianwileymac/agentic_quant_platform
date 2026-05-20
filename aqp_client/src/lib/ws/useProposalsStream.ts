import { useEffect, useState } from "react";

import { useProposalsStore, type AgentProposal } from "@/store/proposals";

import { createWsClient } from "./client";
import type { WsStatus } from "./types";

interface ProposalEnvelope {
  /** Server-side stage marker — `pending` | `approved` | `declined` | `expired` | `executed`. */
  stage?: AgentProposal["status"];
  proposal?: AgentProposal;
}

/**
 * Subscribes the global proposals stream so the Action Center toast
 * and the topbar badge update in real time even when the user isn't
 * on the Action Center route. Mounted once at the App root.
 */
export function useProposalsStream(): WsStatus {
  const [status, setStatus] = useState<WsStatus>("idle");
  const upsert = useProposalsStore((s) => s.upsert);
  const remove = useProposalsStore((s) => s.remove);

  useEffect(() => {
    const client = createWsClient<ProposalEnvelope, never>({
      path: "/agents/proposals/stream",
      reconnect: true,
      onStatus: setStatus,
      onMessage: (env) => {
        if (!env || !env.proposal) return;
        const proposal: AgentProposal = { ...env.proposal };
        if (env.stage) proposal.status = env.stage;
        upsert(proposal);
        if (proposal.status && proposal.status !== "pending") {
          // Keep a brief tail in the store so the recently-actioned
          // proposal is still visible in the Action Center; expire after 60 s.
          setTimeout(() => remove(proposal.id), 60_000);
        }
      },
    });
    return () => client.close();
  }, [upsert, remove]);

  return status;
}
