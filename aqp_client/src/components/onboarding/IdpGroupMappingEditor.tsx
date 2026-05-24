/**
 * Per-org IdP connection + group-mapping editor (Phase 6 of the
 * Auth0 Refactor).
 *
 * Wraps `/tenancy/orgs/{org_id}/idp-connections` +
 * `/tenancy/orgs/{org_id}/idp-group-mappings` so an admin can attach
 * a Google Workspace / AWS IAM Identity Center / Okta / OneLogin /
 * JumpCloud / generic SAML/OIDC connection to an org and map its
 * external groups onto AQP roles.
 *
 * Secret material (client secrets, signing certs) is configured in
 * the Auth0 Dashboard separately — this UI only edits the AQP-side
 * metadata (kind / display name / allowed email domains / group
 * mapping table).
 */
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";

type ConnectionKind =
  | "entra"
  | "google_workspace"
  | "aws_iam_identity_center"
  | "okta"
  | "onelogin"
  | "jumpcloud"
  | "generic_oidc"
  | "generic_saml";

type AqpRole = "viewer" | "editor" | "admin" | "owner";
type ScopeKind = "org" | "team" | "workspace" | "project" | "lab";

interface IdpConnection {
  id: string;
  organization_id: string;
  connection_kind: ConnectionKind;
  auth0_connection_id: string | null;
  display_name: string | null;
  status: string;
  allowed_email_domains: string | null;
  config: Record<string, unknown>;
  created_at: string;
}

interface IdpGroupMapping {
  id: string;
  organization_id: string;
  idp_connection_id: string;
  external_group_name: string;
  aqp_role: AqpRole;
  scope_kind: ScopeKind;
  scope_id: string;
  is_active: boolean;
}

export interface IdpGroupMappingEditorProps {
  organizationId: string;
  organizationName?: string;
}

export function IdpGroupMappingEditor({
  organizationId,
  organizationName,
}: IdpGroupMappingEditorProps) {
  const [connections, setConnections] = useState<IdpConnection[]>([]);
  const [mappings, setMappings] = useState<IdpGroupMapping[]>([]);
  const [loading, setLoading] = useState(true);
  const [addingConnection, setAddingConnection] = useState(false);
  const [newKind, setNewKind] = useState<ConnectionKind>("google_workspace");
  const [newDisplay, setNewDisplay] = useState("");
  const [newAuth0Id, setNewAuth0Id] = useState("");
  const [newDomains, setNewDomains] = useState("");
  const [mapForm, setMapForm] = useState({
    connectionId: "",
    externalGroup: "",
    aqpRole: "viewer" as AqpRole,
    scopeKind: "org" as ScopeKind,
    scopeId: organizationId,
  });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [conns, maps] = await Promise.all([
          apiFetch<IdpConnection[]>(
            `/tenancy/orgs/${organizationId}/idp-connections`,
          ),
          apiFetch<IdpGroupMapping[]>(
            `/tenancy/orgs/${organizationId}/idp-group-mappings`,
          ),
        ]);
        if (!cancelled) {
          setConnections(conns || []);
          setMappings(maps || []);
        }
      } catch (err) {
        if (!cancelled) {
          toast.error(
            err instanceof Error ? err.message : "Failed to load IdP config.",
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
  }, [organizationId]);

  const createConnection = async () => {
    try {
      const created = await apiFetch<IdpConnection>(
        `/tenancy/orgs/${organizationId}/idp-connections`,
        {
          method: "POST",
          body: JSON.stringify({
            connection_kind: newKind,
            display_name: newDisplay.trim() || null,
            auth0_connection_id: newAuth0Id.trim() || null,
            allowed_email_domains: newDomains.trim() || null,
            config: {},
          }),
        },
      );
      setConnections((prev) => [created, ...prev]);
      setAddingConnection(false);
      setNewDisplay("");
      setNewAuth0Id("");
      setNewDomains("");
      toast.success(`IdP connection (${newKind}) created in pending state.`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to create IdP connection.",
      );
    }
  };

  const revokeConnection = async (id: string) => {
    if (!window.confirm("Revoke this IdP connection? Users signing in via this IdP will lose org membership.")) {
      return;
    }
    try {
      await apiFetch(
        `/tenancy/orgs/${organizationId}/idp-connections/${id}`,
        { method: "DELETE" },
      );
      setConnections((prev) =>
        prev.map((c) => (c.id === id ? { ...c, status: "revoked" } : c)),
      );
      toast.success("IdP connection revoked.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to revoke.");
    }
  };

  const createMapping = async () => {
    if (!mapForm.connectionId || !mapForm.externalGroup.trim() || !mapForm.scopeId.trim()) {
      toast.warning("Connection, external group, and scope ID are required.");
      return;
    }
    try {
      const created = await apiFetch<IdpGroupMapping>(
        `/tenancy/orgs/${organizationId}/idp-group-mappings`,
        {
          method: "POST",
          body: JSON.stringify({
            idp_connection_id: mapForm.connectionId,
            external_group_name: mapForm.externalGroup.trim(),
            aqp_role: mapForm.aqpRole,
            scope_kind: mapForm.scopeKind,
            scope_id: mapForm.scopeId.trim(),
          }),
        },
      );
      setMappings((prev) => [created, ...prev]);
      setMapForm((prev) => ({ ...prev, externalGroup: "" }));
      toast.success("Group mapping added.");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to add group mapping.",
      );
    }
  };

  const deleteMapping = async (id: string) => {
    try {
      await apiFetch(
        `/tenancy/orgs/${organizationId}/idp-group-mappings/${id}`,
        { method: "DELETE" },
      );
      setMappings((prev) => prev.filter((m) => m.id !== id));
      toast.success("Group mapping deleted.");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete mapping.",
      );
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>IdP connections</CardTitle>
              <p className="mt-1 text-sm text-[color:var(--text-muted)]">
                {organizationName
                  ? `External identity providers attached to ${organizationName}.`
                  : "External identity providers attached to this org."}
              </p>
            </div>
            {!addingConnection && (
              <Button size="sm" onClick={() => setAddingConnection(true)} className="gap-2">
                <Plus className="h-4 w-4" />
                Add connection
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {addingConnection && (
            <div className="rounded-lg border border-[color:var(--border)] p-3 space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="flex flex-col gap-1 text-sm">
                  <span>IdP kind</span>
                  <select
                    className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
                    value={newKind}
                    onChange={(e) => setNewKind(e.target.value as ConnectionKind)}
                  >
                    <option value="entra">Microsoft Entra</option>
                    <option value="google_workspace">Google Workspace</option>
                    <option value="aws_iam_identity_center">AWS IAM Identity Center</option>
                    <option value="okta">Okta</option>
                    <option value="onelogin">OneLogin</option>
                    <option value="jumpcloud">JumpCloud</option>
                    <option value="generic_oidc">Generic OIDC</option>
                    <option value="generic_saml">Generic SAML</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span>Display name</span>
                  <input
                    type="text"
                    className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
                    value={newDisplay}
                    onChange={(e) => setNewDisplay(e.target.value)}
                    placeholder="Acme Google Workspace"
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span>Auth0 connection id (optional)</span>
                  <input
                    type="text"
                    className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
                    value={newAuth0Id}
                    onChange={(e) => setNewAuth0Id(e.target.value)}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span>Allowed email domains (CSV)</span>
                  <input
                    type="text"
                    className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
                    value={newDomains}
                    onChange={(e) => setNewDomains(e.target.value)}
                    placeholder="acme.com,acme.io"
                  />
                </label>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setAddingConnection(false)}>
                  Cancel
                </Button>
                <Button size="sm" onClick={createConnection}>
                  Save (pending)
                </Button>
              </div>
            </div>
          )}
          {loading && (
            <div className="text-sm text-[color:var(--text-muted)]">Loading...</div>
          )}
          {!loading && connections.length === 0 && (
            <div className="text-sm text-[color:var(--text-muted)]">
              No IdP connections configured.
            </div>
          )}
          {connections.map((conn) => (
            <div
              key={conn.id}
              className="flex items-center justify-between rounded border border-[color:var(--border)] p-3"
            >
              <div>
                <div className="text-sm font-semibold">
                  {conn.display_name || conn.connection_kind}{" "}
                  <span className="text-xs text-[color:var(--text-muted)]">
                    ({conn.status})
                  </span>
                </div>
                <div className="text-xs text-[color:var(--text-muted)]">
                  Kind: {conn.connection_kind} ·{" "}
                  Allowed domains: {conn.allowed_email_domains || "any"} ·{" "}
                  Auth0 id: {conn.auth0_connection_id || "(unset)"}
                </div>
              </div>
              {conn.status !== "revoked" && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => revokeConnection(conn.id)}
                  className="gap-2 text-[color:var(--danger)]"
                >
                  <Trash2 className="h-4 w-4" />
                  Revoke
                </Button>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Group mappings</CardTitle>
          <p className="mt-1 text-sm text-[color:var(--text-muted)]">
            Map external IdP group claims to AQP roles. The post-login Action
            reads these mappings and upserts membership rows on every sign-in.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
            <select
              className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
              value={mapForm.connectionId}
              onChange={(e) =>
                setMapForm((p) => ({ ...p, connectionId: e.target.value }))
              }
            >
              <option value="">Pick connection</option>
              {connections
                .filter((c) => c.status !== "revoked")
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.display_name || c.connection_kind}
                  </option>
                ))}
            </select>
            <input
              type="text"
              className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
              placeholder="External group name"
              value={mapForm.externalGroup}
              onChange={(e) =>
                setMapForm((p) => ({ ...p, externalGroup: e.target.value }))
              }
            />
            <select
              className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
              value={mapForm.aqpRole}
              onChange={(e) =>
                setMapForm((p) => ({
                  ...p,
                  aqpRole: e.target.value as AqpRole,
                }))
              }
            >
              <option value="viewer">viewer</option>
              <option value="editor">editor</option>
              <option value="admin">admin</option>
              <option value="owner">owner</option>
            </select>
            <select
              className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
              value={mapForm.scopeKind}
              onChange={(e) =>
                setMapForm((p) => ({
                  ...p,
                  scopeKind: e.target.value as ScopeKind,
                }))
              }
            >
              <option value="org">org</option>
              <option value="team">team</option>
              <option value="workspace">workspace</option>
              <option value="project">project</option>
              <option value="lab">lab</option>
            </select>
            <input
              type="text"
              className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
              placeholder="Scope ID"
              value={mapForm.scopeId}
              onChange={(e) =>
                setMapForm((p) => ({ ...p, scopeId: e.target.value }))
              }
            />
          </div>
          <Button onClick={createMapping} className="gap-2">
            <Plus className="h-4 w-4" />
            Add mapping
          </Button>
          {mappings.length === 0 ? (
            <div className="text-sm text-[color:var(--text-muted)]">
              No group mappings yet.
            </div>
          ) : (
            <ul className="divide-y divide-[color:var(--border)]">
              {mappings.map((mapping) => (
                <li
                  key={mapping.id}
                  className="flex items-center justify-between py-2 text-sm"
                >
                  <div>
                    <span className="font-mono text-xs">
                      {mapping.external_group_name}
                    </span>{" "}
                    →{" "}
                    <span className="font-semibold">{mapping.aqp_role}</span>{" "}
                    on {mapping.scope_kind} <span className="font-mono text-xs">{mapping.scope_id}</span>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteMapping(mapping.id)}
                    className="gap-2 text-[color:var(--danger)]"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
