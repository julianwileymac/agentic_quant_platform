"use client";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

export default function KubernetesPage() {
  const { data } = useQuery({
    queryKey: ["admin", "kubernetes", "status"],
    queryFn: () => adminGet<Record<string, unknown>>("/kubernetes/status"),
    refetchInterval: 10_000,
  });
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Kubernetes</h1>
        <p className="text-sm text-muted-foreground">
          Cluster status proxied through the registered{" "}
          <code>KubernetesAdapter</code> per AGENTS rule 28.
        </p>
      </header>
      <pre className="rounded-md border bg-white p-4 text-xs">
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
    </div>
  );
}
