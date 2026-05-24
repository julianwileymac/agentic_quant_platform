/**
 * Org-admin invite wizard (AGENTS rule 44 — B2B onboarding).
 *
 * Wraps the existing `/tenancy/invites` CRUD endpoints so an org
 * admin can send invitations to teammates with a chosen role +
 * scope (org / workspace / team). The backend creates a
 * :class:`TenancyInvite` row (HMAC-hashed token) and returns the
 * one-time raw token in the response body so the admin can either
 * email it or copy-paste a deep link.
 *
 * Per the credential-safety rule, the raw token is shown ONCE in
 * the modal and never persisted to client state beyond the modal
 * close — refreshing the page drops it. The hash on the backend is
 * the authoritative artifact.
 */
import { Mail } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";

interface InviteCreatePayload {
  email: string;
  organization_id: string;
  workspace_id?: string;
  team_id?: string;
  role: "viewer" | "editor" | "admin" | "owner";
  message?: string;
}

interface InviteCreateResponse {
  id: string;
  raw_token: string;
  accept_url: string;
  organization_id: string;
  workspace_id?: string | null;
  team_id?: string | null;
  email: string;
  role: string;
}

export interface OrgInviteWizardProps {
  organizationId: string;
  organizationName?: string;
  /** Default workspace_id to scope the invite to. Pass null for org-level. */
  workspaceId?: string | null;
}

export function OrgInviteWizard({
  organizationId,
  organizationName,
  workspaceId,
}: OrgInviteWizardProps) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InviteCreatePayload["role"]>("viewer");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [lastInvite, setLastInvite] = useState<InviteCreateResponse | null>(null);

  const submit = async () => {
    if (!email.trim()) {
      toast.warning("Email is required.");
      return;
    }
    setSending(true);
    try {
      const payload: InviteCreatePayload = {
        email: email.trim().toLowerCase(),
        organization_id: organizationId,
        role,
        ...(workspaceId ? { workspace_id: workspaceId } : {}),
        ...(message.trim() ? { message: message.trim() } : {}),
      };
      const response = await apiFetch<InviteCreateResponse>("/tenancy/invites", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setLastInvite(response);
      setEmail("");
      setMessage("");
      toast.success(`Invite sent to ${response.email}.`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to send invite.",
      );
    } finally {
      setSending(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invite a teammate</CardTitle>
        <p className="mt-1 text-sm text-[color:var(--text-muted)]">
          {organizationName
            ? `Send an invite to join ${organizationName}.`
            : "Send an invite to your organization."}{" "}
          The invitee receives a one-time accept link valid for the configured
          TTL.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label className="flex flex-col gap-1 text-sm md:col-span-2">
            <span>Email</span>
            <input
              type="email"
              className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="teammate@example.com"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span>Role</span>
            <select
              className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
              value={role}
              onChange={(e) =>
                setRole(e.target.value as InviteCreatePayload["role"])
              }
            >
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
              <option value="admin">Admin</option>
              <option value="owner">Owner</option>
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span>
            Personal message{" "}
            <span className="text-xs text-[color:var(--text-muted)]">(optional)</span>
          </span>
          <textarea
            className="rounded border border-[color:var(--border)] bg-transparent px-2 py-1.5 text-sm"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={2}
          />
        </label>
        <div className="flex justify-end">
          <Button onClick={submit} disabled={sending} className="gap-2">
            <Mail className="h-4 w-4" />
            {sending ? "Sending..." : "Send invite"}
          </Button>
        </div>

        {lastInvite && (
          <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--bg-elevated)] p-3 space-y-2">
            <div className="text-sm font-semibold">One-time accept link</div>
            <code className="block break-all rounded bg-[color:var(--bg-base)] p-2 text-xs">
              {lastInvite.accept_url}
            </code>
            <p className="text-xs text-[color:var(--text-muted)]">
              Share this link via email or a secure channel. The token is shown
              once; refreshing the page drops it. The server stores only the
              hash.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(lastInvite.accept_url);
                  toast.success("Link copied to clipboard.");
                } catch {
                  toast.warning(
                    "Clipboard unavailable; copy the link manually.",
                  );
                }
              }}
            >
              Copy link
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
