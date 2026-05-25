import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import {
  adminApi,
  type CloudflareConnectBody,
} from "@/lib/api";

type CloudflareWizardProps = {
  onConnected(): void;
};

export function CloudflareWizard({ onConnected }: CloudflareWizardProps) {
  const [step, setStep] = useState(1);
  const [serviceId, setServiceId] = useState("aqp-admin");
  const [namespace, setNamespace] = useState("");
  const [accountId, setAccountId] = useState("");
  const [zoneId, setZoneId] = useState("");
  const [teamDomain, setTeamDomain] = useState("");
  const [triggerRestart, setTriggerRestart] = useState(true);
  const [localError, setLocalError] = useState<string | null>(null);

  const connect = useMutation<
    {
      service_id: string;
      namespace: string | null;
      config_result: unknown;
      cloudflare_health: Record<string, unknown> | null;
      cloudflare_health_error: Record<string, unknown> | null;
      audit_run_id: string | null;
    },
    Error,
    CloudflareConnectBody
  >({
    mutationFn: async (body) => adminApi.connectCloudflare(body),
    onSuccess() {
      setLocalError(null);
      onConnected();
    },
    onError(err) {
      setLocalError(err.message);
    },
  });

  function nextStep() {
    if (!accountId.trim()) {
      setLocalError("Cloudflare account id is required.");
      return;
    }
    setLocalError(null);
    setStep(2);
  }

  function connectAccount() {
    connect.mutate({
      service_id: serviceId.trim() || "aqp-admin",
      namespace: namespace.trim() || undefined,
      account_id: accountId.trim(),
      zone_id: zoneId.trim() || undefined,
      team_domain: teamDomain.trim() || undefined,
      trigger_restart: triggerRestart,
    });
  }

  return (
    <div className="space-y-4 rounded-lg border bg-card p-6">
      <header>
        <h3 className="text-lg font-medium">Cloudflare connection wizard</h3>
        <p className="text-sm text-muted-foreground">
          Persist Cloudflare account settings and verify health.
        </p>
      </header>

      <div className="text-xs text-slate-500">Step {step} of 2</div>

      {step === 1 ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <div className="text-xs font-medium text-slate-500">Service id</div>
              <input
                className="w-full rounded border px-3 py-2 text-sm"
                value={serviceId}
                onChange={(e) => setServiceId(e.target.value)}
                placeholder="aqp-admin"
              />
            </label>
            <label className="space-y-1">
              <div className="text-xs font-medium text-slate-500">
                Namespace <span className="text-slate-400">(optional)</span>
              </div>
              <input
                className="w-full rounded border px-3 py-2 text-sm"
                value={namespace}
                onChange={(e) => setNamespace(e.target.value)}
                placeholder="aqp"
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <div className="text-xs font-medium text-slate-500">Cloudflare account id</div>
              <input
                className="w-full rounded border px-3 py-2 text-sm"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                placeholder="account-id"
              />
            </label>
            <label className="space-y-1">
              <div className="text-xs font-medium text-slate-500">
                Zone id <span className="text-slate-400">(optional)</span>
              </div>
              <input
                className="w-full rounded border px-3 py-2 text-sm"
                value={zoneId}
                onChange={(e) => setZoneId(e.target.value)}
                placeholder="zone-id"
              />
            </label>
          </div>
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">
              Team domain <span className="text-slate-400">(optional)</span>
            </div>
            <input
              className="w-full rounded border px-3 py-2 text-sm"
              value={teamDomain}
              onChange={(e) => setTeamDomain(e.target.value)}
              placeholder="your-team.cloudflareaccess.com"
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={triggerRestart}
              onChange={(e) => setTriggerRestart(e.target.checked)}
            />
            <span>Trigger service restart after applying config</span>
          </label>
          <div className="flex justify-end">
            <button
              type="button"
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
              onClick={nextStep}
            >
              Review
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="rounded border bg-slate-50 p-3 text-xs">
            <div className="mb-2 font-semibold">Review payload</div>
            <pre className="max-h-48 overflow-auto">
              {JSON.stringify(
                {
                  service_id: serviceId,
                  namespace: namespace || undefined,
                  account_id: accountId,
                  zone_id: zoneId || undefined,
                  team_domain: teamDomain || undefined,
                  trigger_restart: triggerRestart,
                },
                null,
                2,
              )}
            </pre>
          </div>
          <div className="flex justify-between">
            <button
              type="button"
              className="rounded-md border px-4 py-2 text-sm"
              onClick={() => setStep(1)}
            >
              Back
            </button>
            <button
              type="button"
              disabled={connect.isPending}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              onClick={connectAccount}
            >
              {connect.isPending ? "Connecting..." : "Connect Cloudflare"}
            </button>
          </div>
        </div>
      )}

      {localError ? <p className="text-sm text-red-600">{localError}</p> : null}
      {connect.data ? (
        <div className="rounded border bg-green-50 p-3 text-xs text-green-900">
          <div className="font-semibold">Connection result</div>
          <pre className="mt-2 max-h-44 overflow-auto">
            {JSON.stringify(connect.data, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
