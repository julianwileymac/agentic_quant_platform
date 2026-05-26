"use client";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type Org = { id: string; name: string; tenancy_strategy?: string | null };

export default function AccountsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "accounts", "organizations"],
    queryFn: () => adminGet<{ organizations: Org[] }>("/accounts/organizations"),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Organizations</h1>
      <div className="overflow-hidden rounded-md border bg-white">
        <table className="min-w-full divide-y">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Tenancy strategy</th>
              <th className="px-4 py-2">ID</th>
            </tr>
          </thead>
          <tbody className="divide-y text-sm">
            {isLoading ? (
              <tr>
                <td colSpan={3} className="px-4 py-3 text-muted-foreground">
                  loading…
                </td>
              </tr>
            ) : (
              (data?.organizations ?? []).map((org) => (
                <tr key={org.id}>
                  <td className="px-4 py-2 font-medium">{org.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {org.tenancy_strategy ?? "—"}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">{org.id}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
