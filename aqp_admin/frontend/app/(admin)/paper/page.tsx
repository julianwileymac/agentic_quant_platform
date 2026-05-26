"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type Run = {
  id: string;
  config_name: string;
  status: string;
  dry_run?: boolean;
  started_at?: string;
};

export default function PaperPage() {
  const { data } = useQuery({
    queryKey: ["admin", "paper", "runs"],
    queryFn: () => adminGet<{ runs: Run[] }>("/paper/runs?limit=50"),
    refetchInterval: 10_000,
  });
  const runs = data?.runs ?? [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Paper trading</h1>
        <p className="text-sm text-muted-foreground">
          Lifecycle proxy to the monolith&apos;s paper-trading runtime. Use the
          kill switch in the topbar for emergency halts; <code>/admin/halt/all</code>
          fans out to every halt URL in parallel.
        </p>
      </header>
      <div className="overflow-hidden rounded-md border bg-white">
        <table className="min-w-full divide-y text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Run</th>
              <th className="px-4 py-2">Config</th>
              <th className="px-4 py-2">Mode</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Started</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {runs.map((run) => (
              <tr key={run.id}>
                <td className="px-4 py-2 font-mono text-xs">
                  <Link href={`/paper/${run.id}`}>{run.id}</Link>
                </td>
                <td className="px-4 py-2">{run.config_name}</td>
                <td className="px-4 py-2">
                  {run.dry_run ? (
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                      DRY RUN
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">live</span>
                  )}
                </td>
                <td className="px-4 py-2">{run.status}</td>
                <td className="px-4 py-2 font-mono text-xs">{run.started_at ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
