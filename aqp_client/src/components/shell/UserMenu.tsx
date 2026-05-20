import { Building2, KeyRound, LogOut, Settings, UserRound } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useApiQuery } from "@/lib/api/hooks";
import type { WhoAmI } from "@/lib/api/tenancy";
import { useAuth } from "@/lib/auth";

import { OrgSwitcher } from "@/components/onboarding/OrgSwitcher";

export function UserMenu() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [orgSwitcherOpen, setOrgSwitcherOpen] = useState(false);

  const whoami = useApiQuery<WhoAmI>({
    queryKey: ["auth", "whoami", "user-menu"],
    path: "/auth/whoami",
    select: (raw) => raw as WhoAmI,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const displayName = user.name ?? whoami.data?.display_name ?? user.email ?? "User";
  const displayEmail = user.email ?? whoami.data?.email ?? "unknown@aqp.local";
  const initials = displayName
    .split(/\s+/)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .slice(0, 2)
    .join("");

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-2">
            {user.picture ? (
              <img
                src={user.picture}
                alt={displayName}
                className="size-6 rounded-full border border-[var(--border-default)] object-cover"
                referrerPolicy="no-referrer"
              />
            ) : (
              <span className="flex size-6 items-center justify-center rounded-full bg-[var(--bg-elevated)] text-[10px] font-semibold">
                {initials || <UserRound className="size-3.5" />}
              </span>
            )}
            <span className="hidden max-w-[140px] truncate text-xs md:inline">{displayName}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel className="space-y-1">
            <div className="truncate text-sm font-semibold">{displayName}</div>
            <div className="truncate text-xs font-normal text-[var(--text-secondary)]">
              {displayEmail}
            </div>
            <Badge variant="outline" className="w-fit">
              {whoami.data?.auth_provider ?? "auth0"}
            </Badge>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault();
              navigate("/auth/profile?tab=profile");
            }}
          >
            <Settings className="size-4" />
            Account settings
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault();
              navigate("/auth/profile?tab=security");
            }}
          >
            <KeyRound className="size-4" />
            Security & MFA
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault();
              navigate("/auth/profile?tab=sessions");
            }}
          >
            <UserRound className="size-4" />
            Sessions
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault();
              setOrgSwitcherOpen(true);
            }}
          >
            <Building2 className="size-4" />
            Switch organization
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault();
              void logout();
            }}
          >
            <LogOut className="size-4" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <OrgSwitcher open={orgSwitcherOpen} onOpenChange={setOrgSwitcherOpen} />
    </>
  );
}
