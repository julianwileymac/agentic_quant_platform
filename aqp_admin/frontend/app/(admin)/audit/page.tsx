"use client";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type AuditRow = {
  run_id: string;
  action: string;
  target: string;
  actor_sub: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
};

export default function AuditPage() {
  const { data } = useQuery({
    queryKey: ["admin", "audit", "runs"],
    queryFn: () => adminGet<{ runs: AuditRow[] }>("/audit/runs?limit=200"),
    refetchInterval: 15_000,
  });
  const rows = data?.runs ?? [];
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Audit ledger</h1>
      <div className="overflow-hidden rounded-md border bg-white">
        <table className="min-w-full divide-y text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Started</th>
              <th className="px-4 py-2">Action</th>
              <th className="px-4 py-2">Target</th>
              <th className="px-4 py-2">Actor</th>
              <th className="px-4 py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((row) => (
              <tr key={row.run_id}>
                <td className="px-4 py-2 font-mono text-xs">{row.started_at}</td>
                <td className="px-4 py-2 font-mono text-xs">{row.action}</td>
                <td className="px-4 py-2 font-mono text-xs">{row.target}</td>
                <td className="px-4 py-2 font-mono text-xs">{row.actor_sub}</td>
                <td className="px-4 py-2">{row.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
