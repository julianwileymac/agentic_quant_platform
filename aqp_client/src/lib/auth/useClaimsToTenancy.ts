import { useEffect } from "react";

import { useAuth } from "./useAuth";
import { useTenancyStore } from "@/store/tenancy";

/**
 * Hydrate the tenancy store from Auth0 custom claims after login.
 *
 * The Auth0 Action (see ``aqp_docs/docs/concepts/identity/auth0-actions.md``) injects
 * ``https://aqp.internal/org_id``, ``https://aqp.internal/team_id``,
 * ``https://aqp.internal/workspace_id``, and
 * ``https://aqp.internal/roles`` into the access token (canonical
 * namespace per ADR 003). The legacy ``https://aqp/`` namespace is
 * still read for one release. On the first render after login we copy
 * those values
 * onto :func:`useTenancyStore` so:
 *
 * - the API client sends the matching ``X-AQP-*`` headers on the
 *   very next request;
 * - the ContextBar renders the user's home org / team / workspace
 *   without an extra round-trip.
 *
 * Idempotent: subsequent renders re-check the claims; if the user
 * changes context manually the hook doesn't fight them (it only
 * writes when the store still holds the *default* seed value).
 */
export function useClaimsToTenancy() {
  const { claims, isAuthenticated, enabled } = useAuth();
  const orgId = useTenancyStore((s) => s.orgId);
  const teamId = useTenancyStore((s) => s.teamId);
  const workspaceId = useTenancyStore((s) => s.workspaceId);
  const setOrg = useTenancyStore((s) => s.setOrg);
  const setUser = useTenancyStore((s) => s.setUser);
  const setWorkspace = useTenancyStore((s) => s.setWorkspace);

  useEffect(() => {
    if (!enabled || !isAuthenticated) return;
    // Only override the deterministic default seed; never stomp on
    // user-chosen tenancy from the ContextBar.
    if (claims.orgId && orgId === "00000000-0000-0000-0000-000000000001") {
      setOrg(claims.orgId);
    }
    if (claims.teamId && teamId === "00000000-0000-0000-0000-000000000002") {
      // setUser doesn't exist for team in the current store — use the
      // dedicated setter when we add it. For now the team field flows
      // from the org via the Auth0 Action so this branch is rarely hit.
      // Placeholder for future setTeam wiring.
    }
    if (
      claims.workspaceId &&
      workspaceId === "00000000-0000-0000-0000-000000000004"
    ) {
      setWorkspace(claims.workspaceId);
    }
  }, [
    enabled,
    isAuthenticated,
    claims.orgId,
    claims.teamId,
    claims.workspaceId,
    orgId,
    teamId,
    workspaceId,
    setOrg,
    setUser,
    setWorkspace,
  ]);
}
