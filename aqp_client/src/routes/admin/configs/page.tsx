import { Eraser, RefreshCcw, Save } from "lucide-react";
import { useEffect, useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import {
  clearConfigLayer,
  getConfigLayer,
  getEffectiveConfig,
  setConfigLayer,
} from "@/lib/api/tenancy";
import { useTenancyStore } from "@/store/tenancy";

const SCOPES = [
  { value: "global", label: "Global (read-only)", readOnly: true },
  { value: "org", label: "Organization" },
  { value: "team", label: "Team" },
  { value: "user", label: "User" },
  { value: "workspace", label: "Workspace" },
  { value: "project", label: "Project" },
  { value: "lab", label: "Lab" },
] as const;

const NAMESPACES = ["llm", "rag", "risk", "agent", "compute", "iceberg", "alpha_vantage"];

type ScopeKind = (typeof SCOPES)[number]["value"];
type Conflict = "first" | "last" | "error";

export function LayeredConfigsRoute() {
  const tenancy = useTenancyStore();
  const [scope, setScope] = useState<ScopeKind>("workspace");
  const [scopeId, setScopeId] = useState<string>(tenancy.workspaceId ?? "");
  const [namespace, setNamespace] = useState<string>("llm");
  const [layerJson, setLayerJson] = useState<string>("{}");
  const [effectiveJson, setEffectiveJson] = useState<string>("{}");
  const [conflict, setConflict] = useState<Conflict>("last");
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<"save" | "clear" | null>(null);

  // Re-bind scopeId default whenever scope changes.
  useEffect(() => {
    const fallback: Record<string, string | null> = {
      global: null,
      org: tenancy.orgId,
      team: tenancy.teamId,
      user: tenancy.userId,
      workspace: tenancy.workspaceId,
      project: tenancy.projectId,
      lab: tenancy.labId,
    };
    setScopeId(fallback[scope] ?? "");
  }, [scope, tenancy.orgId, tenancy.teamId, tenancy.userId, tenancy.workspaceId, tenancy.projectId, tenancy.labId]);

  const isGlobal = scope === "global";

  const load = async () => {
    setLoading(true);
    try {
      const eff = await getEffectiveConfig(namespace);
      setEffectiveJson(JSON.stringify(eff, null, 2));
      if (!isGlobal && scopeId) {
        const layer = await getConfigLayer(scope, scopeId, namespace);
        setLayerJson(JSON.stringify(layer, null, 2));
      } else {
        setLayerJson("{}");
      }
      toast.success("Loaded");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Load failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const submitSave = async () => {
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(layerJson);
    } catch (err) {
      toast.error(`Invalid JSON: ${(err as Error).message}`);
      return;
    }
    setLoading(true);
    try {
      const res = await setConfigLayer(scope, scopeId, namespace, payload, conflict);
      toast.success(`Overlay ${res.overlay_id.slice(0, 8)} persisted`);
      await load();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Save failed: ${msg}`);
    } finally {
      setLoading(false);
      setPendingAction(null);
    }
  };

  const submitClear = async () => {
    setLoading(true);
    try {
      await clearConfigLayer(scope, scopeId, namespace);
      toast.success("Layer cleared");
      await load();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Clear failed: ${msg}`);
    } finally {
      setLoading(false);
      setPendingAction(null);
    }
  };

  return (
    <PageContainer
      title="Layered Config"
      subtitle="Cascading config overlays per tenancy scope. Save / Clear are friction-gated; layered configs cascade and a bad payload at workspace scope can break every project."
      extra={
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
            <RefreshCcw className="h-4 w-4" /> Load
          </Button>
          <Button variant="warn" size="sm" onClick={() => setPendingAction("clear")} disabled={isGlobal || !scopeId} className="gap-2">
            <Eraser className="h-4 w-4" /> Clear layer
          </Button>
          <Button size="sm" onClick={() => setPendingAction("save")} disabled={isGlobal || !scopeId} className="gap-2">
            <Save className="h-4 w-4" /> Save
          </Button>
        </div>
      }
    >
      <Card className="mb-3">
        <CardContent className="grid grid-cols-1 gap-3 py-3 lg:grid-cols-4">
          <div className="flex flex-col gap-1">
            <Label htmlFor="cfg-scope">Scope</Label>
            <select
              id="cfg-scope"
              value={scope}
              onChange={(e) => setScope(e.target.value as ScopeKind)}
              className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
            >
              {SCOPES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="cfg-id">Scope id</Label>
            <Input
              id="cfg-id"
              className="font-mono"
              value={scopeId}
              onChange={(e) => setScopeId(e.target.value)}
              disabled={isGlobal}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="cfg-ns">Namespace</Label>
            <select
              id="cfg-ns"
              value={namespace}
              onChange={(e) => setNamespace(e.target.value)}
              className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
            >
              {NAMESPACES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <Label>Conflict policy</Label>
            <div className="grid grid-cols-3 gap-1">
              {(["first", "last", "error"] as const).map((c) => (
                <Button
                  key={c}
                  type="button"
                  size="sm"
                  variant={conflict === c ? "default" : "outline"}
                  onClick={() => setConflict(c)}
                  className="capitalize"
                >
                  {c}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card className="h-[calc(100vh-360px)]">
          <CardHeader>
            <CardTitle>Layer ({scope})</CardTitle>
            {isGlobal ? <Badge variant="secondary">read-only</Badge> : <Badge variant="warn">editable</Badge>}
          </CardHeader>
          <CardContent className="h-full p-3">
            <CodeEditor value={layerJson} onChange={setLayerJson} language="json" readOnly={isGlobal} />
          </CardContent>
        </Card>
        <Card className="h-[calc(100vh-360px)]">
          <CardHeader>
            <CardTitle>Effective</CardTitle>
            <Badge variant="secondary">merged · read-only</Badge>
          </CardHeader>
          <CardContent className="h-full p-3">
            <CodeEditor value={effectiveJson} language="json" readOnly />
          </CardContent>
        </Card>
      </div>

      {pendingAction === "save" ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(o) => !o && setPendingAction(null)}
          title={`Save ${namespace} overlay at ${scope} scope`}
          consequence={`This persists the overlay at ${scope}/${scopeId}. Cascading downstream — every scope below this one will see the merged effective config on the next read.`}
          details={[
            { label: "Scope", value: scope },
            { label: "Scope id", value: scopeId, tone: "warn" },
            { label: "Namespace", value: namespace },
            { label: "Conflict policy", value: conflict },
          ]}
          confirmPhrase="OVERRIDE"
          confirmLabel="Save overlay"
          confirmVariant="warn"
          onConfirm={submitSave}
        />
      ) : null}

      {pendingAction === "clear" ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(o) => !o && setPendingAction(null)}
          title={`Clear ${namespace} overlay at ${scope} scope`}
          consequence={`This deletes the overlay row at ${scope}/${scopeId}. The effective config falls through to the next scope above. This is irreversible.`}
          details={[
            { label: "Scope", value: scope },
            { label: "Scope id", value: scopeId, tone: "warn" },
            { label: "Namespace", value: namespace },
          ]}
          confirmPhrase="CLEAR"
          confirmLabel="Clear overlay"
          confirmVariant="destructive"
          onConfirm={submitClear}
        />
      ) : null}
    </PageContainer>
  );
}
