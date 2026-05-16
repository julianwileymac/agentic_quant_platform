import { LogOut, ShieldCheck, User as UserIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import { useAuth } from "@/lib/auth";

interface WhoAmIResponse {
  id: string;
  email: string;
  display_name: string;
  auth_provider: string;
  auth_subject: string | null;
  avatar_url: string | null;
  workspaces: { id: string; role: string | null }[];
  projects: { id: string; role: string | null }[];
  labs: { id: string; role: string | null }[];
  active_context: Record<string, unknown>;
}

/**
 * ``/auth/profile`` — read-only summary of who the user is + every
 * Membership row the backend can find. Phase 6 of the multi-tenant
 * rollout shipped this as the click-through target from the
 * ``IdentityChip`` menu so users can audit their own scope chain.
 */
export function ProfileRoute() {
  const { user, claims, logout } = useAuth();
  const whoami = useApiQuery<WhoAmIResponse>({
    queryKey: ["auth", "whoami"],
    path: "/auth/whoami",
  });

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-3">
            {user.picture ? (
              <img
                alt=""
                src={user.picture}
                className="size-12 rounded-full border border-[var(--border)]"
              />
            ) : (
              <div className="flex size-12 items-center justify-center rounded-full bg-[var(--bg-sidebar)]">
                <UserIcon className="size-6 text-[var(--text-muted)]" />
              </div>
            )}
            <div>
              <CardTitle>{user.name || user.email || "Anonymous"}</CardTitle>
              <CardDescription className="font-mono text-xs">
                {user.id}
              </CardDescription>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => void logout()}>
            <LogOut className="mr-2 size-4" /> Sign out
          </Button>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
          <Field label="Email" value={whoami.data?.email ?? user.email ?? "—"} />
          <Field
            label="Provider"
            value={whoami.data?.auth_provider ?? "local"}
          />
          <Field
            label="Auth subject"
            value={whoami.data?.auth_subject ?? user.id ?? "—"}
            mono
          />
          <Field
            label="Roles (from JWT)"
            value={claims.roles.length ? claims.roles.join(", ") : "viewer"}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4" /> Memberships
          </CardTitle>
          <CardDescription>
            Postgres ``memberships`` rows that grant access. Add / remove via
            the admin pages under ``/admin``.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <MembershipBlock
            label="Workspaces"
            rows={whoami.data?.workspaces ?? []}
          />
          <MembershipBlock label="Projects" rows={whoami.data?.projects ?? []} />
          <MembershipBlock label="Labs" rows={whoami.data?.labs ?? []} />
        </CardContent>
      </Card>
    </div>
  );
}

interface FieldProps {
  label: string;
  value: string;
  mono?: boolean;
}

function Field({ label, value, mono }: FieldProps) {
  return (
    <div className="space-y-0.5">
      <div className="text-[10px] font-mono uppercase text-[var(--text-muted)]">
        {label}
      </div>
      <div className={mono ? "font-mono text-xs" : ""}>{value}</div>
    </div>
  );
}

interface MembershipBlockProps {
  label: string;
  rows: { id: string; role: string | null }[];
}

function MembershipBlock({ label, rows }: MembershipBlockProps) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-mono uppercase text-[var(--text-muted)]">
        {label}
      </div>
      {rows.length === 0 ? (
        <div className="text-xs text-[var(--text-muted)]">No {label.toLowerCase()}.</div>
      ) : (
        <ul className="space-y-1">
          {rows.map((row) => (
            <li
              key={row.id}
              className="flex items-center justify-between rounded border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-1 font-mono text-xs"
            >
              <span>{row.id}</span>
              <Badge variant="outline">{row.role ?? "viewer"}</Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
