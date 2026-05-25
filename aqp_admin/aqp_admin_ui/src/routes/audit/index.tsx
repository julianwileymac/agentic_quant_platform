import { useQuery } from "@tanstack/react-query";

import { adminApi } from "@/lib/api";

export function AuditIndex() {
  const audit = useQuery({
    queryKey: ["audit-runs"],
    queryFn: () => adminApi.listAuditRuns(200),
    refetchInterval: 15000,
  });

  return (
    <section className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Audit</h1>
        <p className="text-sm text-muted-foreground">
          Recent admin audit rows. Mutating admin actions write a pending row
          before dispatch and a finish row after completion.
        </p>
      </header>

      <div className="overflow-hidden rounded-lg border bg-card">
        {audit.isLoading ? <p className="p-4 text-sm">Loading audit rows...</p> : null}
        {audit.error ? (
          <p className="p-4 text-sm text-red-600">{audit.error.message}</p>
        ) : null}
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Phase</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Target</th>
              <th className="px-3 py-2">Run</th>
            </tr>
          </thead>
          <tbody>
            {(audit.data?.runs ?? []).map((run, idx) => (
              <tr key={`${run.run_id ?? "run"}-${idx}`} className="border-t">
                <td className="px-3 py-2">{String(run.phase ?? "n/a")}</td>
                <td className="px-3 py-2">{String(run.status ?? "n/a")}</td>
                <td className="px-3 py-2 font-mono text-xs">{String(run.action ?? "")}</td>
                <td className="px-3 py-2">{String(run.target ?? "")}</td>
                <td className="px-3 py-2 font-mono text-xs">{String(run.run_id ?? "")}</td>
              </tr>
            ))}
            {audit.data?.runs.length === 0 ? (
              <tr>
                <td className="px-3 py-6 text-center text-slate-500" colSpan={5}>
                  No audit rows yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
