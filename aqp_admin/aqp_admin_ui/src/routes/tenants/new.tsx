/**
 * Tenant vending wizard.
 *
 * Phase 1.7 of the control-plane maturation. Collects:
 *
 * 1. Org name + slug + plan (B2B / B2C / internal / sandbox).
 * 2. Entra tenant id (B2B primary path).
 * 3. Tenant namespace spec (quotas + PSA + network mode).
 * 4. Optional hosted-PaaS Terraform toggle (deferred).
 *
 * The submit fans out through the admin BFF
 * (``POST /admin/tenants``) which:
 *
 *  - Audit-writes the run BEFORE upstream calls.
 *  - Brokers a ``data.tenancy.link_org_to_entra_tenant`` (B2B path).
 *  - Brokers a ``POST /manage/tenants/{tenant_id}/provision`` to the
 *    control plane.
 */
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { adminApi, type TenantVendingResponse } from "@/lib/api";

type Plan = "b2b" | "b2c" | "internal" | "sandbox";

export function TenantVendingWizard() {
  const [orgId, setOrgId] = useState("");
  const [orgName, setOrgName] = useState("");
  const [plan, setPlan] = useState<Plan>("b2b");
  const [entraTenantId, setEntraTenantId] = useState("");
  const [enablePaas, setEnablePaas] = useState(false);

  const mutation = useMutation<TenantVendingResponse, Error, void>({
    mutationFn: async () =>
      adminApi.vendTenant({
        org_id: orgId,
        org_name: orgName,
        plan,
        entra_tenant_id: entraTenantId || undefined,
        enable_paas_terraform: enablePaas,
      }),
  });

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Vend a new tenant</h1>
      <p className="text-sm text-muted-foreground">
        Multi-step provisioning: link Entra tenant (B2B), bootstrap the
        Kubernetes namespace, optionally apply the hosted-PaaS Terraform
        stack. Audit-first — every step writes a row to the admin
        audit ledger before dispatching.
      </p>
      <form
        className="space-y-4 rounded-lg border bg-card p-6"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-4">
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">Org slug (DNS-safe)</div>
            <input
              required
              pattern="[a-z0-9-]+"
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              placeholder="acme-research"
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">Display name</div>
            <input
              required
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="Acme Research Capital"
            />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">Plan</div>
            <select
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={plan}
              onChange={(e) => setPlan(e.target.value as Plan)}
            >
              <option value="b2b">B2B (Entra-primary)</option>
              <option value="b2c">B2C (Auth0 fallback)</option>
              <option value="internal">Internal</option>
              <option value="sandbox">Sandbox</option>
            </select>
          </label>
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">
              Entra tenant id <span className="text-slate-400">(B2B)</span>
            </div>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={entraTenantId}
              onChange={(e) => setEntraTenantId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              disabled={plan !== "b2b"}
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enablePaas}
            onChange={(e) => setEnablePaas(e.target.checked)}
          />
          <span>Provision hosted-PaaS infrastructure (Terraform; deferred)</span>
        </label>
        <button
          type="submit"
          disabled={mutation.isPending || !orgId || !orgName}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {mutation.isPending ? "Provisioning..." : "Vend tenant"}
        </button>
        {mutation.isError ? (
          <p className="text-sm text-red-600">{mutation.error.message}</p>
        ) : null}
      </form>

      {mutation.data ? <PhasesPanel data={mutation.data} /> : null}
    </section>
  );
}

function PhasesPanel({ data }: { data: TenantVendingResponse }) {
  return (
    <div className="rounded-lg border bg-card p-6">
      <header className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Vending result for {data.org_id}</h2>
        <span
          className={
            data.success
              ? "rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700"
              : "rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700"
          }
        >
          {data.success ? "succeeded" : "partial"}
        </span>
      </header>
      <ol className="space-y-2">
        {data.phases.map((phase, idx) => (
          <li key={idx} className="rounded border p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{phase.phase}</span>
              <span
                className={
                  phase.status === "succeeded"
                    ? "text-green-700"
                    : phase.status === "failed"
                      ? "text-red-700"
                      : "text-slate-500"
                }
              >
                {phase.status}
              </span>
            </div>
            {phase.error ? (
              <pre className="mt-2 overflow-auto rounded bg-slate-50 p-2 text-xs">
                {String(phase.error)}
              </pre>
            ) : null}
          </li>
        ))}
      </ol>
      {data.audit_run_id ? (
        <p className="mt-4 text-xs text-muted-foreground">
          audit_run_id: <code>{data.audit_run_id}</code>
        </p>
      ) : null}
    </div>
  );
}
