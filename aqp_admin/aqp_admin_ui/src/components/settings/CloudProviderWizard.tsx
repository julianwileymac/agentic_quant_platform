import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import {
  adminApi,
  type CloudProviderConnectBody,
} from "@/lib/api";

type CloudProviderWizardProps = {
  providerKind: "aws" | "azure" | "gcp";
  onConnected(): void;
};

const LABELS: Record<CloudProviderWizardProps["providerKind"], string> = {
  aws: "AWS",
  azure: "Azure",
  gcp: "GCP",
};

export function CloudProviderWizard({
  providerKind,
  onConnected,
}: CloudProviderWizardProps) {
  const [step, setStep] = useState(1);
  const [slug, setSlug] = useState<string>(providerKind);
  const [name, setName] = useState(`${LABELS[providerKind]} account`);
  const [defaultRegion, setDefaultRegion] = useState("");
  const [credentialKey, setCredentialKey] = useState("");
  const [configJson, setConfigJson] = useState("{}");
  const [validationError, setValidationError] = useState<string | null>(null);

  const connect = useMutation<
    { provider: Record<string, unknown>; audit_run_id: string | null },
    Error,
    CloudProviderConnectBody
  >({
    mutationFn: async (body) => adminApi.connectCloudProvider(body),
    onSuccess() {
      setValidationError(null);
      onConnected();
    },
    onError(err) {
      setValidationError(err.message);
    },
  });

  function nextStep() {
    if (!slug.trim() || !name.trim()) {
      setValidationError("Slug and display name are required.");
      return;
    }
    setValidationError(null);
    setStep(2);
  }

  function connectProvider() {
    let parsedConfig: Record<string, unknown> = {};
    try {
      parsedConfig = JSON.parse(configJson || "{}") as Record<string, unknown>;
    } catch {
      setValidationError("Config JSON must be valid JSON.");
      return;
    }
    connect.mutate({
      provider_kind: providerKind,
      slug: slug.trim(),
      name: name.trim(),
      default_region: defaultRegion.trim() || undefined,
      credential_key: credentialKey.trim() || undefined,
      config_json: parsedConfig,
    });
  }

  return (
    <div className="space-y-4 rounded-lg border bg-card p-6">
      <header>
        <h3 className="text-lg font-medium">{LABELS[providerKind]} connection wizard</h3>
        <p className="text-sm text-muted-foreground">
          Register a Terraform provider record for this cloud account.
        </p>
      </header>

      <div className="text-xs text-slate-500">Step {step} of 2</div>

      {step === 1 ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <div className="text-xs font-medium text-slate-500">Provider slug</div>
              <input
                className="w-full rounded border px-3 py-2 text-sm"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder={`${providerKind}-primary`}
              />
            </label>
            <label className="space-y-1">
              <div className="text-xs font-medium text-slate-500">Display name</div>
              <input
                className="w-full rounded border px-3 py-2 text-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={`${LABELS[providerKind]} production`}
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <div className="text-xs font-medium text-slate-500">
                Default region <span className="text-slate-400">(optional)</span>
              </div>
              <input
                className="w-full rounded border px-3 py-2 text-sm"
                value={defaultRegion}
                onChange={(e) => setDefaultRegion(e.target.value)}
                placeholder={providerKind === "aws" ? "us-east-1" : providerKind === "azure" ? "eastus" : "us-central1"}
              />
            </label>
            <label className="space-y-1">
              <div className="text-xs font-medium text-slate-500">
                Credential key <span className="text-slate-400">(optional)</span>
              </div>
              <input
                className="w-full rounded border px-3 py-2 text-sm"
                value={credentialKey}
                onChange={(e) => setCredentialKey(e.target.value)}
                placeholder={`idp:${providerKind}:prod`}
              />
            </label>
          </div>
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">
              Provider config JSON <span className="text-slate-400">(optional)</span>
            </div>
            <textarea
              className="min-h-24 w-full rounded border px-3 py-2 font-mono text-xs"
              value={configJson}
              onChange={(e) => setConfigJson(e.target.value)}
              placeholder='{"environment":"production"}'
            />
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
                  provider_kind: providerKind,
                  slug,
                  name,
                  default_region: defaultRegion || undefined,
                  credential_key: credentialKey || undefined,
                  config_json: (() => {
                    try {
                      return JSON.parse(configJson || "{}");
                    } catch {
                      return configJson;
                    }
                  })(),
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
              onClick={connectProvider}
            >
              {connect.isPending ? "Connecting..." : `Connect ${LABELS[providerKind]}`}
            </button>
          </div>
        </div>
      )}

      {validationError ? <p className="text-sm text-red-600">{validationError}</p> : null}
      {connect.data ? (
        <div className="rounded border bg-green-50 p-3 text-xs text-green-900">
          <div className="font-semibold">Connected</div>
          <pre className="mt-2 max-h-44 overflow-auto">
            {JSON.stringify(connect.data, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
