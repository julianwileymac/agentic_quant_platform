"use client";

import { useQuery } from "@tanstack/react-query";

import { adminApi } from "@/lib/api/client";

export default function DashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "health"],
    queryFn: () => adminApi.health(),
    refetchInterval: 15_000,
  });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Health-check + at-a-glance topology for the admin BFF.
        </p>
      </header>
      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-md border bg-white p-4">
          <div className="text-xs uppercase text-muted-foreground">Service</div>
          <div className="text-lg font-semibold">aqp-admin</div>
          <div className="text-xs text-muted-foreground">port :8900</div>
        </div>
        <div className="rounded-md border bg-white p-4">
          <div className="text-xs uppercase text-muted-foreground">Health</div>
          <div className="text-lg font-semibold">
            {isLoading ? "…" : isError ? "unreachable" : data?.status ?? "unknown"}
          </div>
          <div className="text-xs text-muted-foreground">
            {data?.version ? `version ${data.version}` : "polling /admin/health"}
          </div>
        </div>
        <div className="rounded-md border bg-white p-4">
          <div className="text-xs uppercase text-muted-foreground">Auth</div>
          <div className="text-lg font-semibold">Entra-primary</div>
          <div className="text-xs text-muted-foreground">Auth0 fallback available</div>
        </div>
      </section>
    </div>
  );
}
