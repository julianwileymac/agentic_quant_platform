"use client";

import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

type Role = { role: string; scopes: string[] };

export default function RbacPage() {
  const { data: roles } = useQuery({
    queryKey: ["admin", "rbac", "roles"],
    queryFn: () => adminGet<{ roles: Role[] }>("/rbac/roles"),
  });
  const { data: scopes } = useQuery({
    queryKey: ["admin", "rbac", "scopes"],
    queryFn: () =>
      adminGet<{ scopes: string[]; by_role: Record<string, string[]> }>(
        "/rbac/scopes",
      ),
  });
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">RBAC</h1>
        <p className="text-sm text-muted-foreground">
          Canonical 4-role lattice: <code>aqp-viewer</code> →{" "}
          <code>aqp-operator</code> → <code>aqp-admin</code> →{" "}
          <code>aqp-superadmin</code>. Bound to the existing{" "}
          <code>Membership</code> table per AGENTS rule 27. (No Casbin.)
        </p>
      </header>
      <section>
        <h2 className="mb-2 text-sm font-semibold">Roles</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {(roles?.roles ?? []).map((role) => (
            <div key={role.role} className="rounded-md border bg-white p-4">
              <div className="font-mono text-sm font-semibold">{role.role}</div>
              <div className="mt-2 text-xs text-muted-foreground">
                {role.scopes.length} scopes
              </div>
              <ul className="mt-2 max-h-40 overflow-y-auto text-xs">
                {role.scopes.map((scope) => (
                  <li key={scope} className="font-mono">
                    {scope}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2 className="mb-2 text-sm font-semibold">All scopes</h2>
        <div className="rounded-md border bg-white p-4 text-xs font-mono">
          {(scopes?.scopes ?? []).join(" · ")}
        </div>
      </section>
    </div>
  );
}
