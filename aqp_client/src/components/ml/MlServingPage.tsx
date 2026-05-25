import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { MlApi, type MlServingSession } from "@/lib/api/ml";

/**
 * Continuous-batching session dashboard.
 *
 * Mirrors the operator dashboard the report describes: every active
 * `ml_serving_sessions` row visible in one table, with a per-session
 * halt button that fans into `ServeHandler.stop_session`. The topbar
 * `KillSwitch` already fans out to `POST /ml/serving/halt-all`; this
 * page is the targeted view.
 */
export function MlServingPage() {
  const [sessions, setSessions] = useState<MlServingSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    MlApi.servingSessions()
      .then((payload) => {
        setSessions(payload.sessions);
        setError(null);
      })
      .catch((exc: Error) => {
        setError(exc.message ?? "failed to load sessions");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 5000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const handleHaltAll = async () => {
    try {
      const result = await MlApi.haltAllServing();
      // eslint-disable-next-line no-alert
      window.alert(`halted ${result.halted} session(s)`);
      refresh();
    } catch (exc) {
      // eslint-disable-next-line no-alert
      window.alert(`halt failed: ${(exc as Error).message}`);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">ML Serving Sessions</h1>
          <p className="text-muted-foreground text-sm">
            Active continuous-batching sessions managed by{" "}
            <code>ServeHandler</code>. Refreshes every 5 seconds.
          </p>
        </div>
        <Button variant="destructive" size="sm" onClick={handleHaltAll}>
          Halt all
        </Button>
      </header>

      {error ? (
        <div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <table className="w-full text-sm">
        <thead className="text-left text-muted-foreground">
          <tr>
            <th className="px-2 py-1">Session</th>
            <th className="px-2 py-1">Model alias</th>
            <th className="px-2 py-1">Class</th>
            <th className="px-2 py-1 text-right">Batch</th>
            <th className="px-2 py-1 text-right">Wait (ms)</th>
            <th className="px-2 py-1 text-right">Pending</th>
            <th className="px-2 py-1 text-right">Served</th>
            <th className="px-2 py-1">Started</th>
            <th className="px-2 py-1">Halted</th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.session_id} className="border-t">
              <td className="px-2 py-1 font-mono text-xs">
                {s.session_id.slice(0, 8)}…
              </td>
              <td className="px-2 py-1">{s.model_alias}</td>
              <td className="px-2 py-1">{s.model_class}</td>
              <td className="px-2 py-1 text-right tabular-nums">{s.max_batch_size}</td>
              <td className="px-2 py-1 text-right tabular-nums">{s.max_wait_ms}</td>
              <td className="px-2 py-1 text-right tabular-nums">{s.pending}</td>
              <td className="px-2 py-1 text-right tabular-nums">{s.served}</td>
              <td className="px-2 py-1 text-xs">{s.started_at}</td>
              <td className="px-2 py-1">{s.halted ? "yes" : "no"}</td>
            </tr>
          ))}
          {!loading && sessions.length === 0 ? (
            <tr>
              <td colSpan={9} className="px-2 py-4 text-center text-muted-foreground">
                No active serving sessions.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
