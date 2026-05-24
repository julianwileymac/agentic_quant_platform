import { useQuery } from "@tanstack/react-query";

import { adminApi } from "@/lib/api";

export function DashboardRoute() {
  const health = useQuery({ queryKey: ["health"], queryFn: adminApi.health });
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
      <p className="text-muted-foreground">
        Internal-only overview of accounts and managed services.
      </p>
      <div className="rounded-lg border bg-card p-6">
        <h2 className="mb-2 text-lg font-medium">Backend health</h2>
        {health.isLoading && <p>Loading...</p>}
        {health.error && <p className="text-destructive">Error: {String(health.error)}</p>}
        {health.data && (
          <pre className="text-sm font-mono">{JSON.stringify(health.data, null, 2)}</pre>
        )}
      </div>
    </section>
  );
}
