"use client";

import { Dropdown } from "antd";
import { Building2, ChevronDown } from "lucide-react";

import { useAuth } from "@/hooks/useAuth";
import { useTenancyStore } from "@/stores/tenancy";

/**
 * Active organization indicator.
 *
 * Sprint 3 keeps this read-only; the full multi-org switch (and
 * Auth0 organization-aware login redirect) lands in Sprint 5 alongside
 * the team management page.
 */
export function OrgSwitcher() {
  const { claims, provider } = useAuth();
  const orgId = useTenancyStore((s) => s.orgId) ?? claims?.orgId ?? "—";

  return (
    <Dropdown
      menu={{
        items: [
          {
            key: "current",
            label: orgId,
            disabled: true,
          },
          { type: "divider" },
          {
            key: "manage",
            label: "Manage organization",
            onClick: () => {
              window.location.href = "/settings/team";
            },
          },
          {
            key: "switch",
            label: `Switch via ${provider === "entra" ? "Microsoft" : "Auth0"} (coming soon)`,
            disabled: true,
          },
        ],
      }}
      trigger={["click"]}
    >
      <button
        type="button"
        className="flex items-center gap-2 rounded px-2 py-1 text-sm transition-colors hover:bg-white/5"
        style={{ color: "var(--text-primary)" }}
      >
        <Building2 size={14} />
        <span className="font-medium">{orgId}</span>
        <ChevronDown size={12} style={{ color: "var(--text-muted)" }} />
      </button>
    </Dropdown>
  );
}
