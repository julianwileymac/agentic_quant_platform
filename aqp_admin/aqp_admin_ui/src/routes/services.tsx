import { useQuery } from "@tanstack/react-query";

import { adminApi } from "@/lib/api";

export function ServicesRoute() {
  const services = useQuery({ queryKey: ["services"], queryFn: adminApi.listServices });
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Managed services</h1>
      <p className="text-muted-foreground">
        Catalog of services AQP offers to customers, with provisioning state.
      </p>
      <div className="rounded-lg border bg-card p-6">
        {services.isLoading && <p>Loading services...</p>}
        {services.data?.services.length === 0 && (
          <p className="text-muted-foreground">No managed services configured yet.</p>
        )}
      </div>
    </section>
  );
}
