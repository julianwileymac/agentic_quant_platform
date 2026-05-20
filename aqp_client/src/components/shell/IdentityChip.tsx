import { LogIn, LogOut, ShieldCheck, User as UserIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";

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

/**
 * Identity chip surfaced on the right edge of the TopBar.
 *
 * In OIDC mode it shows the IdP-supplied avatar / display name and
 * exposes a logout button that clears the SDK cache before
 * redirecting back to the IdP.
 *
 * In local-first mode the chip shows the deterministic ``Local User``
 * + a pseudo-login button that explains how to switch on Auth0
 * (links to the docs anchor).
 */
export function IdentityChip() {
  const navigate = useNavigate();
  const { enabled, isAuthenticated, user, claims, logout, loginWithRedirect } = useAuth();
  // Always pull /auth/whoami so the chip shows the same identity the
  // backend resolved (catches misconfigurations where the SPA thinks
  // a user is logged in but the API rejects the JWT).
  const whoami = useApiQuery<WhoAmI>({
    queryKey: ["auth", "whoami"],
    path: "/auth/whoami",
    select: (raw) => raw as WhoAmI,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const display = user.name || whoami.data?.display_name || "User";
  const email = user.email || whoami.data?.email;
  const picture = user.picture;
  const initials = display
    .split(/\s+/)
    .map((token) => token[0]?.toUpperCase() ?? "")
    .slice(0, 2)
    .join("");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-2 px-2">
          {picture ? (
            <img
              src={picture}
              alt={display}
              referrerPolicy="no-referrer"
              className="h-6 w-6 rounded-full object-cover"
            />
          ) : (
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--bg-elevated)] text-[10px] font-bold text-[var(--text-secondary)]">
              {initials || <UserIcon className="h-3 w-3" />}
            </span>
          )}
          <span className="hidden max-w-[140px] truncate text-xs sm:inline">{display}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="truncate font-medium">{display}</span>
          {email ? (
            <span className="truncate text-[11px] font-normal text-[var(--text-muted)]">
              {email}
            </span>
          ) : null}
          <span className="truncate text-[10px] font-normal text-[var(--text-muted)]">
            via {whoami.data?.auth_provider ?? "local"}
            {claims.roles.length > 0 ? ` · ${claims.roles.join(", ")}` : ""}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={(e) => {
            e.preventDefault();
            navigate("/auth/profile");
          }}
        >
          <ShieldCheck className="h-4 w-4" />
          <span className="flex-1">Profile & memberships</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {enabled && isAuthenticated ? (
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              void logout();
            }}
          >
            <LogOut className="h-4 w-4" />
            <span className="flex-1">Sign out</span>
          </DropdownMenuItem>
        ) : enabled ? (
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              void loginWithRedirect("/");
            }}
          >
            <LogIn className="h-4 w-4" />
            <span className="flex-1">Sign in</span>
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem disabled className="text-xs">
            Local-first mode (no IdP wired)
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
