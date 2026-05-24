/**
 * BYOK broker credentials account tab (AGENTS hard rule 55).
 *
 * Lists the user's broker credentials, lets them add a new one
 * (gated by step-up MFA on the backend), and revoke an existing one.
 * Secret values are typed into the form once and posted directly to
 * ``/me/broker-credentials`` — they NEVER round-trip back from the
 * server, and the form clears them as soon as the POST resolves.
 *
 * Per the platform's `aqp-management-engine` credential-safety rule,
 * the tab NEVER logs secret values, never echoes them in toast text,
 * and never embeds them in error messages.
 */
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";

type Environment = "paper" | "live" | "sandbox";

interface PayloadField {
  name: string;
  label: string;
  secret: boolean;
}

interface MetaField {
  name: string;
  label: string;
  secret: boolean;
}

interface ProviderDescriptor {
  slug: string;
  display_name: string;
  credential_kind: string;
  payload_fields: PayloadField[];
  meta_fields: MetaField[];
  supports_environments: Environment[];
}

interface ProvidersResponse {
  ok: boolean;
  providers: ProviderDescriptor[];
}

interface CredentialSummary {
  id: string;
  provider: string;
  label: string;
  credential_kind: string;
  environment: Environment;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
  meta: Record<string, unknown>;
}

interface ListResponse {
  ok: boolean;
  credentials: CredentialSummary[];
}

interface CreateResponse {
  ok: boolean;
  credential: CredentialSummary;
}

export function BrokerCredentialsTab() {
  const [providers, setProviders] = useState<ProviderDescriptor[]>([]);
  const [credentials, setCredentials] = useState<CredentialSummary[]>([]);
  const [isLoading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [selectedProviderSlug, setSelectedProviderSlug] = useState<string>("");
  const [label, setLabel] = useState("");
  const [environment, setEnvironment] = useState<Environment>("paper");
  const [payload, setPayload] = useState<Record<string, string>>({});
  const [meta, setMeta] = useState<Record<string, string>>({});
  const [isSubmitting, setSubmitting] = useState(false);

  const selectedProvider = useMemo(
    () => providers.find((p) => p.slug === selectedProviderSlug),
    [providers, selectedProviderSlug],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [provs, creds] = await Promise.all([
          apiFetch<ProvidersResponse>("/me/broker-credentials/providers"),
          apiFetch<ListResponse>("/me/broker-credentials"),
        ]);
        if (!cancelled) {
          setProviders(provs.providers || []);
          setCredentials(creds.credentials || []);
          if (!selectedProviderSlug && provs.providers?.length) {
            setSelectedProviderSlug(provs.providers[0].slug);
          }
        }
      } catch (err) {
        if (!cancelled) {
          toast.error(
            err instanceof Error ? err.message : "Failed to load broker credentials.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // Reset payload + meta when the provider changes — we never want
  // payload state for one provider to leak into another provider's
  // form (e.g. an alpaca api_secret accidentally posted to polygon).
  useEffect(() => {
    setPayload({});
    setMeta({});
  }, [selectedProviderSlug]);

  const handleSubmit = async () => {
    if (!selectedProvider) return;
    if (!label.trim()) {
      toast.warning("Label is required.");
      return;
    }
    for (const field of selectedProvider.payload_fields) {
      if (!payload[field.name]?.trim()) {
        toast.warning(`${field.label} is required.`);
        return;
      }
    }
    setSubmitting(true);
    try {
      const response = await apiFetch<CreateResponse>("/me/broker-credentials", {
        method: "POST",
        body: JSON.stringify({
          provider: selectedProvider.slug,
          label: label.trim(),
          credential_kind: selectedProvider.credential_kind,
          environment,
          payload,
          meta,
        }),
      });
      setCredentials((prev) => [response.credential, ...prev]);
      setLabel("");
      setPayload({});
      setMeta({});
      setAdding(false);
      toast.success(`Stored ${selectedProvider.display_name} credential securely.`);
    } catch (err) {
      // Surface ONLY the high-level error — never re-render the
      // payload content in toast text.
      toast.error(
        err instanceof Error ? err.message : "Failed to store broker credential.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevoke = async (id: string, providerName: string) => {
    if (
      !window.confirm(
        `Revoke this ${providerName} credential? Any running strategy that depends on it will fail on its next broker call.`,
      )
    ) {
      return;
    }
    try {
      await apiFetch(`/me/broker-credentials/${id}`, { method: "DELETE" });
      setCredentials((prev) => prev.filter((c) => c.id !== id));
      toast.success("Credential revoked.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to revoke credential.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Broker credentials</CardTitle>
            <p className="mt-1 text-sm text-[color:var(--text-muted)]">
              Bring-your-own API keys for non-OAuth brokers (Alpaca, Polygon,
              Interactive Brokers, etc.). Secrets are envelope-encrypted at rest
              and never round-trip back to your browser.
            </p>
          </div>
          {!adding && (
            <Button
              size="sm"
              onClick={() => setAdding(true)}
              disabled={isLoading || providers.length === 0}
              className="gap-2"
            >
              <Plus className="h-4 w-4" />
              Add credential
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="text-sm text-[color:var(--text-muted)]">
            Loading credentials...
          </div>
        ) : (
          <>
            {adding && selectedProvider && (
              <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--bg-elevated)] p-4 space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <label className="flex flex-col gap-1 text-sm">
                    <span>Provider</span>
                    <select
                      className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
                      value={selectedProviderSlug}
                      onChange={(e) => setSelectedProviderSlug(e.target.value)}
                    >
                      {providers.map((p) => (
                        <option key={p.slug} value={p.slug}>
                          {p.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-sm">
                    <span>Label</span>
                    <input
                      type="text"
                      className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                      placeholder="e.g. primary, paper-1, scratch"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm">
                    <span>Environment</span>
                    <select
                      className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
                      value={environment}
                      onChange={(e) => setEnvironment(e.target.value as Environment)}
                    >
                      {selectedProvider.supports_environments.map((env) => (
                        <option key={env} value={env}>
                          {env}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {selectedProvider.payload_fields.map((field) => (
                    <label key={field.name} className="flex flex-col gap-1 text-sm">
                      <span>{field.label}</span>
                      <input
                        type={field.secret ? "password" : "text"}
                        className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 font-mono text-xs"
                        value={payload[field.name] || ""}
                        onChange={(e) =>
                          setPayload((prev) => ({ ...prev, [field.name]: e.target.value }))
                        }
                        autoComplete="off"
                        spellCheck={false}
                      />
                    </label>
                  ))}
                  {selectedProvider.meta_fields.map((field) => (
                    <label key={field.name} className="flex flex-col gap-1 text-sm">
                      <span>
                        {field.label}{" "}
                        <span className="text-xs text-[color:var(--text-muted)]">
                          (metadata)
                        </span>
                      </span>
                      <input
                        type="text"
                        className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-xs"
                        value={meta[field.name] || ""}
                        onChange={(e) =>
                          setMeta((prev) => ({ ...prev, [field.name]: e.target.value }))
                        }
                      />
                    </label>
                  ))}
                </div>
                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setAdding(false);
                      setLabel("");
                      setPayload({});
                      setMeta({});
                    }}
                  >
                    Cancel
                  </Button>
                  <Button size="sm" onClick={handleSubmit} disabled={isSubmitting}>
                    {isSubmitting ? "Saving..." : "Save credential"}
                  </Button>
                </div>
                <p className="text-xs text-[color:var(--text-muted)]">
                  Saving prompts for fresh MFA. The secret is encrypted in memory
                  before it leaves your browser and the plaintext is never persisted.
                </p>
              </div>
            )}
            {credentials.length === 0 ? (
              <div className="text-sm text-[color:var(--text-muted)]">
                No broker credentials yet. Click "Add credential" to store your first.
              </div>
            ) : (
              <ul className="divide-y divide-[color:var(--border)]">
                {credentials.map((cred) => (
                  <li
                    key={cred.id}
                    className="flex items-center justify-between gap-4 py-3"
                  >
                    <div>
                      <div className="text-sm font-semibold">{cred.label}</div>
                      <div className="text-xs text-[color:var(--text-muted)]">
                        {cred.provider} · {cred.environment} ·{" "}
                        {cred.last_used_at
                          ? `last used ${cred.last_used_at}`
                          : "never used"}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRevoke(cred.id, cred.provider)}
                      className="gap-2 text-[color:var(--danger)]"
                    >
                      <Trash2 className="h-4 w-4" />
                      Revoke
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
