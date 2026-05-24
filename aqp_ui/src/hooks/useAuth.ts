"use client";

import { useAuthClient } from "@/providers/AuthClientProvider";

/**
 * Provider-agnostic auth surface for client components.
 *
 * Mirrors aqp_client/src/lib/auth/useAuth.ts. The provider, user, and
 * namespaced claims are populated by the AuthClientProvider via
 * `/api/auth/me`.
 */
export function useAuth() {
  return useAuthClient();
}
