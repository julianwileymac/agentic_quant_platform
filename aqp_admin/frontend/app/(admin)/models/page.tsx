"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type Model = {
  name: string;
  latest_version?: number;
  aliases?: Record<string, number>;
  last_updated_timestamp?: string;
};

export default function ModelsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "models"],
    queryFn: () => adminGet<{ models: Model[] }>("/models"),
  });
  const models = data?.models ?? [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">MLflow model registry</h1>
        <p className="text-sm text-muted-foreground">
          Champion / challenger administration. Alias moves require step-up MFA per
          AGENTS rule 52.
        </p>
      </header>
      <div className="overflow-hidden rounded-md border bg-white">
        <table className="min-w-full divide-y text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Model</th>
              <th className="px-4 py-2">Latest</th>
              <th className="px-4 py-2">Champion</th>
              <th className="px-4 py-2">Challenger</th>
              <th className="px-4 py-2">Last updated</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-4 py-3 text-muted-foreground">
                  loading…
                </td>
              </tr>
            ) : (
              models.map((model) => (
                <tr key={model.name}>
                  <td className="px-4 py-2 font-medium">
                    <Link href={`/models/${encodeURIComponent(model.name)}`}>
                      {model.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2">{model.latest_version ?? "—"}</td>
                  <td className="px-4 py-2 text-emerald-700">
                    {model.aliases?.champion ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-amber-700">
                    {model.aliases?.challenger ?? "—"}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">
                    {model.last_updated_timestamp ?? "—"}
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
