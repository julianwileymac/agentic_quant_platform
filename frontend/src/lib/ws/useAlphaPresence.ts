import { useEffect, useRef, useState } from "react";

import { createWsClient } from "./client";
import type { WsStatus } from "./types";

export interface AlphaPresenceParticipant {
  participant_id: string;
  display_name: string;
  joined_at: number;
  last_seen: number;
}

interface PresenceEnvelope {
  stage?: "welcome" | "presence";
  participant_id?: string;
  participants?: AlphaPresenceParticipant[];
  count?: number;
}

interface PresenceOutbound {
  stage: "heartbeat" | "update";
  display_name?: string;
}

export interface AlphaPresenceState {
  status: WsStatus;
  /** Server-assigned participant id once the welcome frame lands. */
  selfId: string | null;
  /** Current roster (excludes the local participant for "X others" copy). */
  others: AlphaPresenceParticipant[];
  /** Full roster including the local participant. */
  all: AlphaPresenceParticipant[];
}

/**
 * OOS extension: real-time presence for the Alpha Factor Studio.
 * Subscribes to ``/quant-agents/alpha-factors/presence`` once per
 * mount and exposes the participant roster + connection status.
 *
 * Presence-only — no CRDT, no cursor positions, no shared editor
 * state. The MVP answers "who else is also looking at this surface
 * right now" so concurrent edits at least surface a banner.
 */
export function useAlphaPresence(displayName: string): AlphaPresenceState {
  const [status, setStatus] = useState<WsStatus>("idle");
  const [selfId, setSelfId] = useState<string | null>(null);
  const [roster, setRoster] = useState<AlphaPresenceParticipant[]>([]);
  const clientRef = useRef<ReturnType<typeof createWsClient<PresenceEnvelope, PresenceOutbound>> | null>(null);

  useEffect(() => {
    const params = new URLSearchParams({ display_name: displayName });
    const client = createWsClient<PresenceEnvelope, PresenceOutbound>({
      path: `/quant-agents/alpha-factors/presence?${params.toString()}`,
      reconnect: true,
      onStatus: setStatus,
      heartbeat: { intervalMs: 12_000, payload: { stage: "heartbeat" } },
      onMessage: (env) => {
        if (!env) return;
        if (env.stage === "welcome" && env.participant_id) {
          setSelfId(env.participant_id);
          return;
        }
        if (env.stage === "presence" && Array.isArray(env.participants)) {
          setRoster(env.participants);
        }
      },
    });
    clientRef.current = client;
    return () => {
      client.close();
      clientRef.current = null;
    };
    // displayName changes get propagated via the update message below;
    // we deliberately only open the socket once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push display-name updates without reconnecting.
  useEffect(() => {
    if (!clientRef.current) return;
    clientRef.current.send({ stage: "update", display_name: displayName });
  }, [displayName]);

  const others = selfId ? roster.filter((p) => p.participant_id !== selfId) : roster;

  return { status, selfId, others, all: roster };
}
