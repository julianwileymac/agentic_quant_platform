import { useQuery } from "@tanstack/react-query";

import { adminApi } from "@/lib/api";

export function AccountsRoute() {
  const orgs = useQuery({ queryKey: ["organizations"], queryFn: adminApi.listOrganizations });
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Accounts</h1>
      <p className="text-muted-foreground">Internal directory of customer organizations.</p>
      <div className="rounded-lg border bg-card p-6">
        {orgs.isLoading && <p>Loading organizations...</p>}
        {orgs.data?.organizations.length === 0 && (
          <p className="text-muted-foreground">No organizations yet.</p>
        )}
      </div>
    </section>
  );
}
