"use client";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type Service = {
  id: string;
  namespace?: string | null;
  phase?: string;
  replicas_ready?: number;
  replicas_desired?: number;
};

export default function ServicesPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "services"],
    queryFn: () => adminGet<{ services: Service[] }>("/services"),
    refetchInterval: 10_000,
  });
  const services = data?.services ?? [];
  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Managed services</h1>
          <p className="text-sm text-muted-foreground">
            Lifecycle proxy to the control-plane <code>WorkloadRuntime</code>.
          </p>
        </div>
      </header>
      <div className="overflow-hidden rounded-md border bg-white">
        <table className="min-w-full divide-y text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Service</th>
              <th className="px-4 py-2">Namespace</th>
              <th className="px-4 py-2">Phase</th>
              <th className="px-4 py-2">Replicas</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {isLoading ? (
              <tr>
                <td colSpan={4} className="px-4 py-3 text-muted-foreground">
                  loading…
                </td>
              </tr>
            ) : (
              services.map((svc) => (
                <tr key={svc.id}>
                  <td className="px-4 py-2 font-medium">{svc.id}</td>
                  <td className="px-4 py-2 text-muted-foreground">{svc.namespace ?? "—"}</td>
                  <td className="px-4 py-2">{svc.phase ?? "?"}</td>
                  <td className="px-4 py-2">
                    {svc.replicas_ready ?? "?"} / {svc.replicas_desired ?? "?"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
