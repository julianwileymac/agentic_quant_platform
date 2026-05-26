"use client";

/**
 * Tenant vending wizard — three-phase flow:
 *
 *   1. entra_link — promote a pending EntraTenantLink to active
 *   2. namespace_provision — apply the tenant Namespace + ResourceQuota
 *      + LimitRange + NetworkPolicy bundle via the control plane
 *   3. paas_terraform — kick off the per-tenant Terraform apply
 *
 * The backend phases are atomic and audit-first; this UI just walks
 * the operator through them. Step-up MFA is enforced server-side.
 */

import { useState } from "react";

import { adminPost } from "@/lib/api/client";

type Phase = "entra_link" | "namespace_provision" | "paas_terraform";

const PHASES: readonly Phase[] = [
  "entra_link",
  "namespace_provision",
  "paas_terraform",
];

export default function VendTenantPage() {
  const [phase, setPhase] = useState<Phase>("entra_link");
  const [busy, setBusy] = useState(false);
  const [orgId, setOrgId] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [results, setResults] = useState<Record<string, unknown>>({});

  async function runPhase() {
    setBusy(true);
    try {
      const result = await adminPost<Record<string, unknown>>("/tenants", {
        org_id: orgId,
        tenant_id: tenantId,
        phase,
      });
      setResults((prev) => ({ ...prev, [phase]: result }));
      const next = PHASES[PHASES.indexOf(phase) + 1];
      if (next) setPhase(next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Vend a new tenant</h1>
        <p className="text-sm text-muted-foreground">
          Three-phase wizard: <code>entra_link</code> →{" "}
          <code>namespace_provision</code> → <code>paas_terraform</code>.
        </p>
      </header>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <label className="text-sm">
          <div className="mb-1 text-xs font-medium text-muted-foreground">org_id</div>
          <input
            className="w-full rounded-md border px-3 py-2"
            value={orgId}
            onChange={(e) => setOrgId(e.target.value)}
          />
        </label>
        <label className="text-sm">
          <div className="mb-1 text-xs font-medium text-muted-foreground">tenant_id</div>
          <input
            className="w-full rounded-md border px-3 py-2"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
          />
        </label>
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={busy || !orgId || !tenantId}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          onClick={() => void runPhase()}
        >
          Run phase: <code>{phase}</code>
        </button>
        <span className="text-xs text-muted-foreground">
          step {PHASES.indexOf(phase) + 1} of {PHASES.length}
        </span>
      </div>
      <pre className="rounded-md border bg-white p-4 text-xs">
        {JSON.stringify(results, null, 2)}
      </pre>
    </div>
  );
}
