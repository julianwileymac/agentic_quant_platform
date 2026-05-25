/**
 * Build detail — live WebSocket log stream + Job phase poll.
 *
 * The WS frames follow the canonical AGENTS rule 4 shape:
 *   { task_id, stage, message, timestamp, ...extras }
 *
 * The viewer auto-scrolls + buffers a bounded number of lines so the
 * tab stays responsive on chatty builds.
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { adminApi } from "@/lib/api";

const MAX_LINES = 1000;

type LogFrame = {
  task_id: string;
  stage: string;
  message: string;
  timestamp: number;
  source?: string;
};

export function BuildDetail() {
  const { jobName } = useParams<{ jobName: string }>();
  const job = jobName ?? "";
  const status = useQuery({
    queryKey: ["build-status", job],
    queryFn: () => adminApi.buildStatus(job),
    enabled: !!job,
    refetchInterval: 5000,
  });
  const [frames, setFrames] = useState<LogFrame[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!job) return;
    // The admin BFF proxies through to the CP WS endpoint. In dev the
    // Vite proxy forwards /manage/* upstream; in prod a reverse proxy
    // handles the WS upgrade.
    const url = `${window.location.origin.replace(/^http/, "ws")}/manage/builds/${encodeURIComponent(job)}/logs/stream?follow=true`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onmessage = (evt) => {
      try {
        const frame = JSON.parse(evt.data) as LogFrame;
        setFrames((prev) => {
          const next = [...prev, frame];
          return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next;
        });
      } catch (err) {
        console.warn("malformed log frame", err);
      }
    };
    ws.onerror = (err) => console.warn("build log WS error", err);
    return () => {
      try {
        ws.close();
      } catch {}
      wsRef.current = null;
    };
  }, [job]);

  if (!job) return <p>Missing job name.</p>;
  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{job}</h1>
          <p className="text-xs text-muted-foreground">
            phase: <code>{status.data?.data?.phase ?? "loading..."}</code>
          </p>
        </div>
        <div className="space-x-2 text-xs">
          <span>active: {status.data?.data?.active ?? 0}</span>
          <span>succeeded: {status.data?.data?.succeeded ?? 0}</span>
          <span>failed: {status.data?.data?.failed ?? 0}</span>
        </div>
      </header>
      <pre className="h-[60vh] overflow-auto rounded-lg border bg-slate-950 p-4 text-xs text-green-200">
        {frames.length === 0 ? "(awaiting log frames...)" : null}
        {frames.map((frame, idx) => (
          <div key={idx}>
            <span className="text-slate-500">
              [{frame.stage}]
            </span>{" "}
            {frame.message}
          </div>
        ))}
      </pre>
    </section>
  );
}
