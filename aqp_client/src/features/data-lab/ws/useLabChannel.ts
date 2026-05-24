import { useEffect, useRef, useState } from "react";

import { createWsClient } from "@/lib/ws/client";
import type { WsStatus } from "@/lib/ws/types";

import {
  type LabClientEnvelope,
  type LabServerEnvelope,
  isLabServerEnvelope,
} from "./envelopes";

interface UseLabChannelOptions {
  /** Per-session id used to scope the WS multiplex. */
  sessionId: string | null;
  /** Called for every typed Lab envelope received from the server. */
  onEnvelope?: (env: LabServerEnvelope) => void;
}

export interface LabChannelHandle {
  status: WsStatus;
  /** Subscribe the channel to a run's progress feed (`task_id`). */
  subscribe: (runOrLiveId: string, stream?: "run" | "live") => void;
  /** Unsubscribe. */
  unsubscribe: (runOrLiveId: string, stream?: "run" | "live") => void;
  /** Send a raw client envelope (eda.exec / sim.command). */
  send: (envelope: LabClientEnvelope) => void;
}

/**
 * React Flow consumer hook that wraps the canonical `createWsClient`
 * (which already handles Phase 3a auth + tenancy headers + reconnect
 * + backoff) and surfaces a typed Lab envelope stream.
 *
 * Frontend rule 1 — every WS pipeline must use the rAF-batched
 * throttled consumer. We delegate to the existing client.ts so the
 * Lab inherits that contract automatically.
 */
export function useLabChannel({
  sessionId,
  onEnvelope,
}: UseLabChannelOptions): LabChannelHandle {
  const [status, setStatus] = useState<WsStatus>("idle");
  const clientRef = useRef<ReturnType<
    typeof createWsClient<LabServerEnvelope, LabClientEnvelope>
  > | null>(null);
  const onEnvelopeRef = useRef(onEnvelope);
  onEnvelopeRef.current = onEnvelope;

  useEffect(() => {
    if (!sessionId) {
      setStatus("idle");
      return;
    }
    const client = createWsClient<LabServerEnvelope, LabClientEnvelope>({
      path: `/ws/lab/${encodeURIComponent(sessionId)}`,
      reconnect: true,
      onStatus: setStatus,
      onMessage: (msg) => {
        if (isLabServerEnvelope(msg)) {
          onEnvelopeRef.current?.(msg);
        }
      },
    });
    clientRef.current = client;
    return () => {
      client.close();
      clientRef.current = null;
    };
  }, [sessionId]);

  const subscribe = (id: string, stream: "run" | "live" = "run") => {
    clientRef.current?.send({ kind: "subscribe", stream, id, v: 1 });
  };

  const unsubscribe = (id: string, stream: "run" | "live" = "run") => {
    clientRef.current?.send({ kind: "unsubscribe", stream, id, v: 1 });
  };

  const send = (envelope: LabClientEnvelope) => {
    clientRef.current?.send(envelope);
  };

  return { status, subscribe, unsubscribe, send };
}
