"use client";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type SecretRef = {
  ref: string;
  backend: string;
  kind?: string;
  namespace?: string | null;
  last_rotated_at?: string | null;
  consumers?: string[];
};

export default function SecretsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "secrets"],
    queryFn: () => adminGet<{ secrets: SecretRef[] }>("/secrets"),
  });
  const secrets = data?.secrets ?? [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Secrets</h1>
        <p className="text-sm text-muted-foreground">
          AWS Secrets Manager + ESO. Plaintext is never returned —
          rotations write the new version through the registered backend
          and notify consumers via rolling restart.
        </p>
      </header>
      <div className="overflow-hidden rounded-md border bg-white">
        <table className="min-w-full divide-y text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Reference</th>
              <th className="px-4 py-2">Backend</th>
              <th className="px-4 py-2">Kind</th>
              <th className="px-4 py-2">Namespace</th>
              <th className="px-4 py-2">Last rotated</th>
              <th className="px-4 py-2">Consumers</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-3 text-muted-foreground">
                  loading…
                </td>
              </tr>
            ) : (
              secrets.map((secret) => (
                <tr key={secret.ref}>
                  <td className="px-4 py-2 font-mono text-xs">{secret.ref}</td>
                  <td className="px-4 py-2">{secret.backend}</td>
                  <td className="px-4 py-2 text-muted-foreground">{secret.kind ?? "—"}</td>
                  <td className="px-4 py-2 text-muted-foreground">{secret.namespace ?? "—"}</td>
                  <td className="px-4 py-2 font-mono text-xs">
                    {secret.last_rotated_at ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {(secret.consumers ?? []).length} consumers
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
