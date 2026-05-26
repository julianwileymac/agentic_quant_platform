"use client";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type FrameworkSettings = Record<string, string | number | boolean | null>;

export default function SettingsPage() {
  const { data } = useQuery({
    queryKey: ["admin", "settings", "framework"],
    queryFn: () => adminGet<{ settings: FrameworkSettings }>("/settings/framework"),
  });
  const entries = data?.settings ? Object.entries(data.settings) : [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Framework + cloud onboarding. Mutations broker through the control plane.
        </p>
      </header>
      <section className="rounded-md border bg-white">
        <header className="border-b px-4 py-2 text-sm font-semibold">Framework</header>
        <table className="min-w-full divide-y text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Key</th>
              <th className="px-4 py-2">Value</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {entries.length === 0 ? (
              <tr>
                <td colSpan={2} className="px-4 py-3 text-muted-foreground">
                  loading…
                </td>
              </tr>
            ) : (
              entries.map(([key, value]) => (
                <tr key={key}>
                  <td className="px-4 py-2 font-mono text-xs">{key}</td>
                  <td className="px-4 py-2 font-mono text-xs">
                    {value === null ? "null" : String(value)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
