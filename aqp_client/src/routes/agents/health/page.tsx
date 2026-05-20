import { useEffect, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import {
  type AgentHealthResponse,
  getAgentHealth,
} from "@/lib/api/agentHealth";

const POLL_MS = 5000;

export function AgentHealthRoute() {
  const [data, setData] = useState<AgentHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      getAgentHealth()
        .then((d) => {
          if (!cancelled) {
            setData(d);
            setError(null);
          }
        })
        .catch((err) => {
          if (!cancelled)
            setError(err instanceof Error ? err.message : String(err));
        });
    load();
    const t = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const cards = useMemo(() => {
    if (!data) return [];
    return [
      { label: "Running", value: data.running, tone: "info" },
      { label: "Pending", value: data.pending, tone: "warn" },
      {
        label: "Halted (24h)",
        value: data.halted_last_24h,
        tone: "neg",
      },
      {
        label: "Stalled candidates",
        value: data.stalled_candidates.length,
        tone: data.stalled_candidates.length > 0 ? "neg" : "info",
      },
    ];
  }, [data]);

  return (
    <PageContainer
      title="Agent run health"
      subtitle="Watchdog snapshot — running / pending / halted / stalled"
    >
      {error ? (
        <p className="text-xs text-[var(--neg-fg)]">{error}</p>
      ) : !data ? (
        <p className="text-xs text-[var(--text-secondary)]">Loading…</p>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {cards.map((c) => (
              <div
                key={c.label}
                className="rounded-md border border-[var(--border-default)] bg-[var(--bg-card)] p-3"
              >
                <p className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">
                  {c.label}
                </p>
                <p
                  className="mt-1 text-base font-semibold"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {c.value}
                </p>
              </div>
            ))}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-semibold">
              Stalled candidates ({data.stalled_candidates.length})
            </h3>
            {data.stalled_candidates.length === 0 ? (
              <p className="text-xs text-[var(--text-secondary)]">
                No stalled runs — the watchdog has nothing to do.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-card)]">
                <table
                  className="w-full text-xs"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  <thead className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">
                    <tr>
                      <th className="px-2 py-1.5 text-left">Run</th>
                      <th className="px-2 py-1.5 text-left">Spec</th>
                      <th className="px-2 py-1.5 text-left">Status</th>
                      <th className="px-2 py-1.5 text-left">Started</th>
                      <th className="px-2 py-1.5 text-right">Stalled (s)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.stalled_candidates.map((c) => (
                      <tr
                        key={c.run_id}
                        className="border-t border-[var(--border-muted)]"
                      >
                        <td className="px-2 py-1 font-mono">
                          {c.run_id.slice(0, 8)}
                        </td>
                        <td className="px-2 py-1">{c.spec}</td>
                        <td className="px-2 py-1">{c.status}</td>
                        <td className="px-2 py-1">
                          {c.started_at.slice(0, 19)}
                        </td>
                        <td className="px-2 py-1 text-right text-[var(--neg-fg)]">
                          {c.stalled_seconds}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <p className="text-[10px] text-[var(--text-secondary)]">
            Last scan: {data.last_watchdog_at.slice(0, 19)} — threshold{" "}
            {data.stall_threshold_seconds}s. The top-bar kill-switch
            issues the matching halt; the watchdog cleans up rows the
            runtime never closed.
          </p>
        </div>
      )}
    </PageContainer>
  );
}

export default AgentHealthRoute;
