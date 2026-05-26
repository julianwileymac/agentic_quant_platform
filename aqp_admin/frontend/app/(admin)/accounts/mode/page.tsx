"use client";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type ModeResponse = {
  active_mode: string;
  operator_pinned: boolean;
  live_detection: { mode: string; evidence: Record<string, unknown> };
};

export default function AccountModePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "accounts", "mode"],
    queryFn: () => adminGet<ModeResponse>("/accounts/mode"),
    refetchInterval: 30_000,
  });
  if (isLoading) return <div className="text-sm text-muted-foreground">loading…</div>;
  if (!data) return null;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Account mode</h1>
        <p className="text-sm text-muted-foreground">
          Single- vs multi-account topology detector + operator pin. The
          enable-multi-account wizard runs the landing-zone Terraform
          stack via the existing <code>TerraformRuntime</code> path
          (rule 42).
        </p>
      </header>
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-md border bg-white p-4">
          <div className="text-xs uppercase text-muted-foreground">Active</div>
          <div className="text-lg font-semibold">{data.active_mode}</div>
          <div className="text-xs text-muted-foreground">
            {data.operator_pinned ? "operator-pinned" : "auto-detected"}
          </div>
        </div>
        <div className="rounded-md border bg-white p-4">
          <div className="text-xs uppercase text-muted-foreground">Live detection</div>
          <div className="text-lg font-semibold">{data.live_detection.mode}</div>
          <div className="text-xs text-muted-foreground">
            {Object.keys(data.live_detection.evidence).length} evidence keys
          </div>
        </div>
      </section>
      <section>
        <h2 className="mb-2 text-sm font-semibold">Detector evidence</h2>
        <pre className="rounded-md border bg-white p-4 text-xs">
          {JSON.stringify(data.live_detection.evidence, null, 2)}
        </pre>
      </section>
    </div>
  );
}
