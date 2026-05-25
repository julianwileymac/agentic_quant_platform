import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { adminApi } from "@/lib/api";
import { CloudProviderWizard } from "@/components/settings/CloudProviderWizard";
import { CloudflareWizard } from "@/components/settings/CloudflareWizard";
import { FrameworkSettingsPanel } from "@/components/settings/FrameworkSettingsPanel";

type ProviderTab = "aws" | "azure" | "gcp" | "cloudflare";

export function SettingsRoute() {
  const [providerTab, setProviderTab] = useState<ProviderTab>("aws");
  const framework = useQuery({
    queryKey: ["settings", "framework"],
    queryFn: () => adminApi.getFrameworkSettings(),
  });
  const cloud = useQuery({
    queryKey: ["settings", "cloud", "status"],
    queryFn: () => adminApi.cloudStatus(),
    refetchInterval: 30000,
  });

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Configure the admin framework and connect cloud accounts.
        </p>
      </header>

      <FrameworkSettingsPanel
        data={framework.data}
        isLoading={framework.isLoading}
        error={framework.error}
        onRefresh={() => {
          void framework.refetch();
        }}
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="rounded-lg border bg-card p-6 space-y-3">
          <h2 className="text-lg font-medium">Cloud account status</h2>
          <p className="text-sm text-muted-foreground">
            Status cards refresh every 30 seconds and after each successful connect.
          </p>
          {cloud.isLoading ? <p className="text-sm">Loading cloud status...</p> : null}
          {cloud.error ? (
            <p className="text-sm text-destructive">Error: {String(cloud.error)}</p>
          ) : null}

          <div className="grid grid-cols-1 gap-3">
            <div className="rounded border p-3 text-sm">
              <div className="font-semibold">Control-plane provider</div>
              <div className="text-slate-600">
                {cloud.data?.control_plane_health?.provider ?? "unknown"}
              </div>
              <div className="text-xs text-slate-500">
                status: {cloud.data?.control_plane_health?.status ?? "n/a"}
              </div>
            </div>
            <div className="rounded border p-3 text-sm">
              <div className="font-semibold">Connected Terraform providers</div>
              <ul className="mt-1 space-y-1 text-xs text-slate-600">
                {(cloud.data?.terraform_providers ?? []).length === 0 ? (
                  <li>No AWS/Azure/GCP provider records yet.</li>
                ) : (
                  cloud.data?.terraform_providers.map((provider, idx) => (
                    <li key={`${provider.slug ?? "provider"}-${idx}`}>
                      {(provider.kind ?? "unknown").toUpperCase()} - {provider.slug ?? "n/a"}
                    </li>
                  ))
                )}
              </ul>
            </div>
            <div className="rounded border p-3 text-sm">
              <div className="font-semibold">Cloudflare health</div>
              <pre className="mt-2 max-h-28 overflow-auto rounded bg-slate-50 p-2 text-[11px]">
                {JSON.stringify(cloud.data?.cloudflare_health ?? null, null, 2)}
              </pre>
            </div>
          </div>

          {cloud.data?.errors?.length ? (
            <div className="rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
              <div className="font-semibold">Upstream warning(s)</div>
              <pre className="mt-2 max-h-40 overflow-auto">
                {JSON.stringify(cloud.data.errors, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>

        <div className="space-y-3 rounded-lg border bg-card p-6">
          <div className="flex flex-wrap gap-2">
            {(["aws", "azure", "gcp", "cloudflare"] as const).map((provider) => {
              const active = providerTab === provider;
              return (
                <button
                  key={provider}
                  type="button"
                  className={`rounded-md border px-3 py-1.5 text-xs font-semibold uppercase tracking-wide ${
                    active
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-200 text-slate-700 hover:bg-slate-50"
                  }`}
                  onClick={() => setProviderTab(provider)}
                >
                  {provider}
                </button>
              );
            })}
          </div>

          {providerTab === "cloudflare" ? (
            <CloudflareWizard
              onConnected={() => {
                void cloud.refetch();
              }}
            />
          ) : (
            <CloudProviderWizard
              key={providerTab}
              providerKind={providerTab}
              onConnected={() => {
                void cloud.refetch();
              }}
            />
          )}
        </div>
      </div>
    </section>
  );
}
