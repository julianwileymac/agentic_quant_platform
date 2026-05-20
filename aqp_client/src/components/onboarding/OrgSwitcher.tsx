import { Command } from "cmdk";
import { Building2, Check } from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useApiQuery } from "@/lib/api/hooks";
import type { WhoAmI } from "@/lib/api/tenancy";
import { apiFetch } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";
import { useTenancyStore } from "@/store/tenancy";
import { toast } from "@/components/ui/toast";

interface OrgSwitcherProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface OrgOption {
  id: string;
  label: string;
  role: string;
}

export function OrgSwitcher({ open, onOpenChange }: OrgSwitcherProps) {
  const { claims } = useAuth();
  const currentOrgId = useTenancyStore((state) => state.orgId);
  const setOrg = useTenancyStore((state) => state.setOrg);

  const whoami = useApiQuery<WhoAmI>({
    queryKey: ["auth", "whoami", "org-switcher"],
    path: "/auth/whoami",
    enabled: open,
    select: (raw) => raw as WhoAmI,
  });

  const options = useMemo<OrgOption[]>(() => {
    const mapped = new Map<string, OrgOption>();
    const memberships = whoami.data?.memberships ?? [];
    for (const membership of memberships) {
      if (membership.scope_kind !== "org") continue;
      const id = String(membership.scope_id);
      mapped.set(id, {
        id,
        label: id,
        role: String(membership.role ?? "viewer"),
      });
    }
    if (claims.orgId && !mapped.has(claims.orgId)) {
      mapped.set(claims.orgId, {
        id: claims.orgId,
        label: claims.orgId,
        role: claims.roles[0] ?? "viewer",
      });
    }
    return Array.from(mapped.values());
  }, [claims.orgId, claims.roles, whoami.data?.memberships]);

  const handleSelect = async (orgId: string) => {
    setOrg(orgId);
    try {
      await apiFetch("/tenancy/active", {
        method: "POST",
        body: JSON.stringify({ org_id: orgId }),
      });
    } catch {
      // TODO: remove localStorage fallback when /tenancy/active is always available.
      localStorage.setItem("aqp-active-org", orgId);
    }
    toast.success(`Active organization set to ${orgId}`);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl p-0">
        <Command className="flex flex-col">
          <div className="flex items-center gap-2 border-b border-[var(--border-default)] px-3 py-3">
            <Building2 className="size-4 text-[var(--text-secondary)]" />
            <Command.Input
              autoFocus
              placeholder="Search organizations..."
              className="h-8 w-full bg-transparent text-sm outline-none placeholder:text-[var(--text-muted)]"
            />
          </div>
          <Command.List className="max-h-[360px] overflow-y-auto p-2">
            {whoami.isPending ? (
              <div className="px-2 py-6 text-center text-sm text-[var(--text-secondary)]">
                Loading organizations...
              </div>
            ) : null}
            <Command.Empty className="px-2 py-6 text-center text-sm text-[var(--text-secondary)]">
              No organizations available for this user.
            </Command.Empty>
            <Command.Group heading="Organizations">
              {options.map((option) => (
                <Command.Item
                  key={option.id}
                  value={`${option.id} ${option.role}`}
                  onSelect={() => {
                    void handleSelect(option.id);
                  }}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm data-[selected=true]:bg-[var(--bg-elevated)]"
                >
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate font-mono text-xs">{option.label}</span>
                    <span className="text-[10px] text-[var(--text-secondary)]">
                      role: {option.role}
                    </span>
                  </span>
                  <Badge variant="outline">{option.role}</Badge>
                  {currentOrgId === option.id ? (
                    <Check className="size-4 text-[var(--info-fg)]" />
                  ) : null}
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
