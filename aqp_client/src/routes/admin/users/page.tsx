import { useState } from "react";

import { AdminCrudPage, CrudSheetFooter } from "@/components/admin/AdminCrudPage";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet } from "@/components/ui/sheet";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { createUser, deleteUser, type User } from "@/lib/api/tenancy";
import { formatTime } from "@/lib/utils";

const AUTH_PROVIDERS = ["local", "oauth_google", "oauth_github", "saml"] as const;

export function UsersAdminRoute() {
  const list = useApiQuery<User[]>({
    queryKey: ["users"],
    path: "/users",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  return (
    <AdminCrudPage<User>
      title="Users"
      subtitle="Tenancy users. Memberships across orgs / teams / workspaces / projects / labs are managed separately."
      rows={list.data ?? []}
      loading={list.isPending}
      onRefresh={() => list.refetch()}
      rowKey={(u) => u.id}
      columns={[
        {
          key: "email",
          header: "Email",
          render: (u) => (
            <div className="flex flex-col">
              <span className="font-mono">{u.email}</span>
              <span className="text-[10px] text-[var(--text-muted)]">{u.id}</span>
            </div>
          ),
        },
        { key: "display_name", header: "Display name", render: (u) => u.display_name },
        {
          key: "auth_provider",
          header: "Auth",
          width: 130,
          render: (u) => <Badge variant="secondary">{u.auth_provider}</Badge>,
        },
        {
          key: "status",
          header: "Status",
          width: 100,
          render: (u) => (
            <Badge variant={u.status === "active" ? "positive" : "secondary"}>{u.status}</Badge>
          ),
        },
        {
          key: "last_login_at",
          header: "Last login",
          width: 150,
          align: "right",
          render: (u) => (
            <span className="text-[var(--text-secondary)]">
              {u.last_login_at ? formatTime(u.last_login_at) : "never"}
            </span>
          ),
        },
      ]}
      confirmDeletePhrase={(u) => u.email}
      deleteTitle={(u) => `Delete user ${u.email}`}
      deleteConsequence="Deleting a user revokes all memberships. Outstanding personal API tokens are invalidated. Type the email to confirm."
      onDelete={(u) => deleteUser(u.id)}
      createSheet={({ open, setOpen, onSaved }) => (
        <CreateUserSheet open={open} onClose={() => setOpen(false)} onSaved={onSaved} />
      )}
    />
  );
}

interface CreateUserSheetProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

function CreateUserSheet({ open, onClose, onSaved }: CreateUserSheetProps) {
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [authProvider, setAuthProvider] = useState<(typeof AUTH_PROVIDERS)[number]>("local");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!email.trim() || !displayName.trim()) return;
    setSaving(true);
    try {
      await createUser({
        email: email.trim(),
        display_name: displayName.trim(),
        auth_provider: authProvider,
      });
      toast.success(`User ${email} created`);
      setEmail("");
      setDisplayName("");
      onSaved();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Create failed: ${msg}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="New user"
      footer={
        <CrudSheetFooter
          onCancel={onClose}
          onSubmit={submit}
          saveLabel="Create user"
          saving={saving}
          saveDisabled={!email.trim() || !displayName.trim()}
        />
      }
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor="user-email">Email</Label>
        <Input id="user-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="user-name">Display name</Label>
        <Input id="user-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="user-auth">Auth provider</Label>
        <select
          id="user-auth"
          value={authProvider}
          onChange={(e) => setAuthProvider(e.target.value as (typeof AUTH_PROVIDERS)[number])}
          className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm text-[var(--text-primary)]"
        >
          {AUTH_PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>
    </Sheet>
  );
}
