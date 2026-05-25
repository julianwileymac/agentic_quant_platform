import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  adminApi,
  type FrameworkPatchBody,
  type FrameworkSettingsResponse,
} from "@/lib/api";

type KeyValueEntry = {
  id: string;
  key: string;
  value: string;
};

type FrameworkSettingsPanelProps = {
  data: FrameworkSettingsResponse | undefined;
  isLoading: boolean;
  error: unknown;
  onRefresh(): void;
};

function _entryId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function _defaultEntry() {
  return { id: _entryId(), key: "", value: "" };
}

const SECRETY_KEY_TOKENS = [
  "SECRET",
  "TOKEN",
  "PASSWORD",
  "CLIENT_SECRET",
  "API_KEY",
  "PRIVATE_KEY",
  "JWT",
];

function _seedValues(data: FrameworkSettingsResponse | undefined): KeyValueEntry[] {
  const persisted = data?.persisted_config?.values;
  if (persisted && Object.keys(persisted).length > 0) {
    return Object.entries(persisted).map(([key, value]) => ({
      id: _entryId(),
      key,
      value: String(value),
    }));
  }
  const runtime = data?.runtime_settings ?? {};
  const fallback: Record<string, string> = {};
  const maybeString = (v: unknown) => (typeof v === "string" ? v : "");
  fallback.AQP_ADMIN_API_URL = maybeString(runtime.api_url);
  fallback.AQP_ADMIN_CONTROL_PLANE_URL = maybeString(runtime.control_plane_url);
  fallback.AQP_ADMIN_AUTH_PROVIDER = maybeString(runtime.auth_provider);
  fallback.AQP_ADMIN_AUDIT_SINK = maybeString(runtime.audit_sink);
  const entries = Object.entries(fallback)
    .filter(([, value]) => Boolean(value))
    .map(([key, value]) => ({ id: _entryId(), key, value }));
  return entries.length > 0 ? entries : [_defaultEntry()];
}

export function FrameworkSettingsPanel({
  data,
  isLoading,
  error,
  onRefresh,
}: FrameworkSettingsPanelProps) {
  const [serviceId, setServiceId] = useState("aqp-admin");
  const [namespace, setNamespace] = useState("");
  const [entries, setEntries] = useState<KeyValueEntry[]>([_defaultEntry()]);
  const [deleteKeys, setDeleteKeys] = useState("");
  const [triggerRestart, setTriggerRestart] = useState(true);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setServiceId(data.service_id || "aqp-admin");
    setNamespace(data.namespace ?? "");
    setEntries(_seedValues(data));
  }, [data]);

  const values = useMemo(() => {
    const next: Record<string, string> = {};
    for (const row of entries) {
      const key = row.key.trim();
      if (!key) continue;
      next[key] = row.value;
    }
    return next;
  }, [entries]);

  const save = useMutation<
    { service_id: string; namespace: string | null; result: unknown; audit_run_id: string | null },
    Error,
    FrameworkPatchBody
  >({
    mutationFn: async (body) => adminApi.patchFrameworkSettings(body),
    onSuccess() {
      onRefresh();
      setLocalError(null);
    },
    onError(err) {
      setLocalError(err.message);
    },
  });

  function addEntry() {
    setEntries((prev) => [...prev, _defaultEntry()]);
  }

  function removeEntry(id: string) {
    setEntries((prev) => (prev.length === 1 ? prev : prev.filter((row) => row.id !== id)));
  }

  function updateEntry(id: string, next: Partial<KeyValueEntry>) {
    setEntries((prev) =>
      prev.map((row) => (row.id === id ? { ...row, ...next } : row)),
    );
  }

  function submit() {
    const cleanedDeleteKeys = deleteKeys
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const allKeys = [...Object.keys(values), ...cleanedDeleteKeys];
    const invalidPrefix = allKeys.filter((key) => !key.startsWith("AQP_ADMIN_"));
    if (invalidPrefix.length > 0) {
      setLocalError(`Only AQP_ADMIN_* keys are allowed. Invalid: ${invalidPrefix.join(", ")}`);
      return;
    }
    const secretish = Object.keys(values).filter((key) =>
      SECRETY_KEY_TOKENS.some((token) => key.toUpperCase().includes(token)),
    );
    if (secretish.length > 0) {
      setLocalError(
        `Secret-like keys must use secret refs, not plaintext values: ${secretish.join(", ")}`,
      );
      return;
    }
    save.mutate({
      service_id: serviceId.trim() || "aqp-admin",
      namespace: namespace.trim() || null,
      values,
      delete_keys: cleanedDeleteKeys,
      trigger_restart: triggerRestart,
    });
  }

  return (
    <div className="rounded-lg border bg-card p-6">
      <header className="mb-4">
        <h2 className="text-lg font-medium">Framework settings</h2>
        <p className="text-sm text-muted-foreground">
          Persisted through the control-plane config patch route.
        </p>
      </header>

      {isLoading ? <p className="text-sm">Loading framework settings...</p> : null}
      {error ? (
        <p className="mb-3 text-sm text-destructive">Failed to load: {String(error)}</p>
      ) : null}

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">Service id</div>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm"
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
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={namespace}
              onChange={(e) => setNamespace(e.target.value)}
              placeholder="aqp"
            />
          </label>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
              Config key/value overrides
            </h3>
            <button
              type="button"
              className="rounded border px-2 py-1 text-xs hover:bg-slate-50"
              onClick={addEntry}
            >
              Add key
            </button>
          </div>
          <div className="space-y-2">
            {entries.map((row) => (
              <div key={row.id} className="grid grid-cols-[1fr_1fr_auto] gap-2">
                <input
                  className="rounded border px-2 py-1.5 text-sm"
                  value={row.key}
                  onChange={(e) => updateEntry(row.id, { key: e.target.value })}
                  placeholder="AQP_ADMIN_API_URL"
                />
                <input
                  className="rounded border px-2 py-1.5 text-sm"
                  value={row.value}
                  onChange={(e) => updateEntry(row.id, { value: e.target.value })}
                  placeholder="http://localhost:8000"
                />
                <button
                  type="button"
                  className="rounded border px-2 text-xs hover:bg-slate-50"
                  onClick={() => removeEntry(row.id)}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">
              Delete keys <span className="text-slate-400">(comma separated)</span>
            </div>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={deleteKeys}
              onChange={(e) => setDeleteKeys(e.target.value)}
              placeholder="AQP_ADMIN_OLD_SETTING"
            />
          </label>
          <label className="flex items-center gap-2 self-end text-sm">
            <input
              type="checkbox"
              checked={triggerRestart}
              onChange={(e) => setTriggerRestart(e.target.checked)}
            />
            <span>Trigger rolling restart after patch</span>
          </label>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={save.isPending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            onClick={submit}
          >
            {save.isPending ? "Saving..." : "Save framework settings"}
          </button>
          <button
            type="button"
            className="rounded-md border px-4 py-2 text-sm"
            onClick={onRefresh}
          >
            Refresh
          </button>
        </div>
      </div>

      {localError ? <p className="mt-3 text-sm text-red-600">{localError}</p> : null}
      {save.data ? (
        <div className="mt-4 rounded border bg-slate-50 p-3 text-xs">
          <div className="font-semibold">Last save result</div>
          <pre className="mt-2 max-h-48 overflow-auto">
            {JSON.stringify(save.data, null, 2)}
          </pre>
        </div>
      ) : null}

      {data?.persisted_config_error ? (
        <div className="mt-4 rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
          <div className="font-semibold">Persisted config lookup warning</div>
          <pre className="mt-2 max-h-40 overflow-auto">
            {JSON.stringify(data.persisted_config_error, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
