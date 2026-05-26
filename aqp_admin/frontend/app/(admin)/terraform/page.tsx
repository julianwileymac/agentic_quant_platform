"use client";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type Workspace = {
  id: string;
  slug: string;
  name: string;
  environment: string;
  status?: string;
};

export default function TerraformPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "terraform", "workspaces"],
    queryFn: () =>
      adminGet<{ workspaces: Workspace[] }>("/terraform/workspaces"),
    refetchInterval: 15_000,
  });
  const workspaces = data?.workspaces ?? [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Terraform</h1>
        <p className="text-sm text-muted-foreground">
          Hash-locked stack specs + workspace lifecycle. Apply / destroy go through the
          control-plane <code>TerraformRuntime</code> with 4-eyes approval and
          step-up MFA per AGENTS rule 42.
        </p>
      </header>
      <div className="overflow-hidden rounded-md border bg-white">
        <table className="min-w-full divide-y text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Slug</th>
              <th className="px-4 py-2">Environment</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">ID</th>
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
              workspaces.map((ws) => (
                <tr key={ws.id}>
                  <td className="px-4 py-2 font-medium">{ws.slug}</td>
                  <td className="px-4 py-2">{ws.environment}</td>
                  <td className="px-4 py-2 text-muted-foreground">{ws.status ?? "—"}</td>
                  <td className="px-4 py-2 font-mono text-xs">{ws.id}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
